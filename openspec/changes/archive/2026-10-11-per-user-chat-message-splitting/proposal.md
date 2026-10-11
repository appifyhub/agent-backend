## Why

Blank-line-delimited replies are currently sent as multiple messages. Every outgoing WhatsApp message is billable in this application's operating model, so users need a per-chat choice that avoids unnecessary sends while preserving readable paragraphs.

## What Changes

- Persist a `split_messages` boolean for each user–chat membership and expose it through the existing per-chat settings API.
- Default new memberships to true for Telegram and false for WhatsApp, GitHub, and background chats. Preserve existing choices and the original reviewed migration backfill when integration defaults change.
- When enabled, retain the current paragraph splitting and code/list preservation. When disabled, retain paragraphs in one text message, splitting only when the provider's text limit requires it.
- Use the triggering user's preference for normal replies, command replies, and burst-level error replies in that chat. Keep emoji reactions and independently sent media/notifications unchanged.
- Add a companion settings checkbox labelled “Split replies into separate messages” in `agent-web`; implement that companion change only at its separately reviewed milestone.
- Implement from persistence upward, with existing layer-appropriate tests and an explicit manual-review stop after every milestone.
- At the very end, after the feature/UI review gates, upgrade all backend production and development dependencies through Pipenv and request recreation of any open backend Dependabot PRs. Verify compatibility and stop for final manual review before archiving.

## Capabilities

### New Capabilities

- `per-user-chat-message-splitting`: Persist, configure, and honor a user–chat reply-splitting preference with platform defaults and provider-required size splitting.

### Modified Capabilities

None. The main specification directory currently contains no existing capabilities to amend.

## Impact

- Backend membership DB model, persistence DTO and mapper, repository, membership creation/refresh service, settings API, response mapper, reply mapper, and message-burst delivery callers.
- Existing repository, membership-service, settings-controller, API-model, reply-mapper, and delivery tests, plus shared stubs where needed. No new test files are planned.
- A user-generated Alembic migration and platform-aware backfill. Migration application requires the user's approval; no live database changes are automatic.
- Existing API documentation and relevant OpenSpec artifacts; no pricing or accounting-policy changes.
- Companion frontend settings types, form, and page in `../agent-web`. The frontend milestone uses this backend change directly as its OpenSpec source, as selected by the user.
- Backend `Pipfile`/`Pipfile.lock`, strictly necessary dependency-compatibility fixes, and `@dependabot recreate` comments on open backend Dependabot PRs during the final milestone.
