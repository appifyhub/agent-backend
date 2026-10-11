## Context

See `proposal.md` for motivation. `ChatMembershipDB` already stores settings under the `(user_id, chat_id)` key. `ChatMembershipRepository` accepts and returns the `ChatMembership` dataclass through `chat_membership_mapper`; persistence changes therefore require the matching dataclass field even before domain behavior changes.

`ChatMembershipService` creates memberships and reconstructs them when admin status changes. The settings controller also reconstructs memberships when saving per-chat settings. Both must carry the new preference explicitly once their milestones are implemented.

`DomainLangchainMapper.map_bot_message_to_storage` joins AI content blocks with `CHAT_MESSAGE_DELIMITER` (`\n\n`) and splits them while preserving code blocks and consecutive list items. Its two production callers are the normal/command reply path and burst-level error path in `MessageBurstService`. The burst worker already establishes the triggering author and chat as the DI invoker context. The platform SDKs send one text message per call and perform existing delivery accounting.

The settings frontend is in `../agent-web`: its `UserChatConfig` interface, `ChatSettingsPage` dirty-state/save logic, and `ChatSettingsForm` toggles are the existing integration points. This change's current OpenSpec edit scope covers only the backend repository.

## Goals / Non-Goals

**Goals:**
- Add one durable boolean preference without a second settings mechanism.
- Preserve paragraph text, existing enabled-mode code/list behavior, and explicit user choices across synchronization and settings saves.
- Complete each architectural layer with its tests before requesting manual review.

**Non-Goals:**
- No pricing changes, template-message work, accounting changes, global user preference, chat-admin setting, or automatic inference from pricing.
- No prompt rewrite: the same blank lines remain paragraph formatting when splitting is disabled.
- No changes to independently sent notifications, generated media, or reaction handling.
- No automatic migration generation/application and no frontend edits from the backend-only apply scope.

## Decisions

### 1. Store a non-null boolean on memberships

Add `split_messages` beside the existing membership settings. Use the existing boolean model conventions with ORM and server defaults of true. The dataclass also defaults to true so the generic persistence representation remains consistent. Platform-aware initialization uses integration policy, not a database default that would need to query another table.

A nullable override would require a third state and resolution on every read without offering a requested benefit. A chat-wide preference would not meet the requested user–chat ownership.

### 2. Treat repository tests as the database milestone

The first task changes the DB model, the minimum persistence DTO field, DB/domain mapping, repository upsert, and existing shared stubs. Extend existing save/get/upsert cases in `test/features/chat/membership/test_chat_membership_repo.py` with the new field alongside other settings, retaining existing membership-key coverage rather than adding a flag-only isolation test. Do not create a database-model test file or assert through repository SQL/session internals.

The dataclass field and mapper are necessary persistence plumbing in this milestone, not permission to implement domain defaults or delivery behavior ahead of review. Mapper regressions cover both stub defaults and overrides of every field, explicitly asserting all nine values in the DB intermediate and domain round-trip result. These complementary cases catch mappings that hardcode either default or overridden settings, while repository tests separately cover persistence and isolation.

### 3. Initialize platform defaults once and preserve explicit choices

New Telegram memberships start with true; new WhatsApp, GitHub, and background memberships start with false. `SPLIT_MESSAGES_DEFAULTS` in `integration_config.py` selects each platform's default, and `integrations.resolve_default_split_messages` resolves it for every membership creation path and the later missing-membership delivery fallback. Membership services do not encode platform business policy. Existing membership synchronization/admin-refresh paths carry their stored value rather than recalculate it, including after integration defaults change. The migration freezes the original WhatsApp-false/other-true backfill once, joining `chat_memberships` to `chat_configs` by chat ID.

When delivery has no stored membership, resolve the same platform default locally without creating a membership or doing a remote authorization call. Use the triggering author, consistent with existing invoker settings and delivery payer ownership.

### 4. Keep splitting decisions in the existing reply mapper

Pass an explicit `split_messages` argument to `map_bot_message_to_storage` and migrate all callers/tests when the domain milestone changes that signature; do not add a compatibility alias. Enabled mode uses the current block-preserving delimiter split. Disabled mode uses the joined content as a single logical text message. Keep empty-content handling and unclosed-fence handling consistent. Burst-service regressions verify actual enabled paragraph deliveries and the burst-level error-notification caller through a one-shot shared external-fake failure, without mocking the mapper, service, or SDK or pinning error-banner wording.

Provider-required length splitting is separate from optional paragraph splitting and applies to both modes. Implement it within the existing reply-mapping path, not by changing SDK return contracts or introducing a transport abstraction. Prefer paragraph/newline/word boundaries, with a hard boundary for an oversized uninterrupted span; preserve text order and all user-visible content. When a code fence crosses a required boundary, close/reopen it as needed without exceeding the provider limit. Validate provider-specific length semantics, including Unicode and Telegram entity parsing, before implementing boundary logic.

### 5. Expose the boolean through existing settings contracts

Add a required boolean to `UserChatConfigResponse` and `UserChatConfigPayload`, using the existing full per-chat user-settings payload convention. Update the controller and response mapper without changing authorization: any authorized member can edit their own preference, and no chat-admin permission is required. This is a coordinated API/frontend contract update; missing/invalid values use the existing validation behavior rather than a silent default that resets saved choices.

### 6. Apply the frontend milestone from this change

From the sibling `agent-web` repository, use this backend change directly as the frontend milestone's OpenSpec source, as selected by the user. Add the field to settings types, dirty-state detection, save payloads, and the existing toggle form. Reuse its localization and toggle conventions without adding a checkbox-specific undo interaction. Present the option as a natural chat flow: several shorter messages in quick succession instead of one long reply, with a warning that per-message platforms may cost more. Verify loaded platform defaults, dirty state, and save/reload on the actual page, including a non-admin group member.

### 7. Leave dependency upgrades until the final milestone

After the companion UI review is approved, upgrade all backend production and development dependencies through Pipenv, updating declared constraints and the lockfile together. Use the latest stable versions compatible with the project's Python/runtime requirements and limit application changes to required compatibility fixes. Check open backend Dependabot PRs and post `@dependabot recreate` on each, recording the PR/comment links or that none are open; do not merge or close them. Verify the installed environment, offline application startup and relevant settings/reply paths, focused/full tests, and repository-wide quality checks. Stop for final manual review before archiving either change.


## Risks / Trade-offs

- A new ORM column requires a migration before code is deployed against an existing database → keep generation/application user-controlled and block rollout until the migration is reviewed.
- A true server default alone would leave old WhatsApp memberships enabled → explicitly backfill by platform in the generated migration.
- Reconstructing a membership can reset a false value → exercise synchronization, admin promotion/demotion, and unrelated settings saves in their owning layers.
- Combining paragraphs can exceed provider text limits → implement and exercise mandatory length splitting; do not promise an unconditional single message or truncate content.
- Required API payload fields need a coordinated frontend release → finish and review the companion UI before product rollout; no compatibility shim is introduced.
- Milestone completion is not feature completion → mark only verified tasks complete and stop at each review gate, without claiming reply behavior has changed after the persistence task.

## Migration Plan

1. Implement and verify the first persistence task against isolated SQLite; no live database is touched.
2. The user runs `./tools/db_generate_migration -y` after reviewing the model change. `src/db/alembic/env.py` already imports `ChatMembershipDB`; verify this remains true before generation.
3. Review the generated revision, include the one-time platform-aware backfill, and verify upgrade/downgrade against an isolated migration environment. Do not hand-create an Alembic revision in place of the required generation command.
4. The user approves and runs `./tools/db_apply_migration` before deployment. Finish the subsequent domain, API, delivery, companion UI, and final dependency-upgrade review gates before rolling out the product behavior.
5. Roll back by reverting application/frontend changes before removing the column with the migration downgrade. Removing the column discards saved splitting preferences and requires explicit user approval.

## Review Gates

At every backend milestone: run focused tests, a real offline smoke scenario covering the changed path, the complete offline suite with `pipenv run pytest -v`, and repository-wide Ruff/spacing checks. Fix only issues caused by this change; report unrelated failures without altering unrelated code. Update OpenSpec task status, report evidence and the exact next milestone, and stop until the user explicitly approves continuation.

The initial apply is restricted to task 1.1. User-run migration generation remains task 1.2; do not mark it complete or cross into domain behavior before the user reviews the persistence work.
