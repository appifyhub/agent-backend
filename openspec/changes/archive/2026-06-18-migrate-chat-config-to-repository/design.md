## Context

`chat_configs` is one of the remaining persistence areas using the legacy `db/schema` + `db/crud` pattern. `ChatConfigCRUD` returns `ChatConfigDB` rows, and callers convert those rows with `ChatConfig.model_validate(...)`. That persistence shape leaks into `AuthorizationService`, `SettingsController`, Telegram/WhatsApp data resolvers, integration helpers, SDK code, announcements, and tests.

Newer persistence areas in this codebase use a different boundary:

```
caller
  │
  ▼
repository ─────▶ SQLAlchemy DB model
  │                    ▲
  ▼                    │
domain dataclass ◀──── mapper
```

`UsageRecordRepository`, `PurchaseRecordRepository`, and `ChatMembershipRepository` are the local precedents. They keep SQLAlchemy models at the persistence edge and return feature-level domain dataclasses to callers.

The most sensitive current behavior is in Telegram and WhatsApp chat resolution. Platform updates arrive as partial chat snapshots. When an existing chat is found, remote-owned fields refresh from the snapshot while DB-owned settings such as language, reply chance, release notifications, and media mode stay intact. `is_private` is treated as a platform fact and updates existing chats when the snapshot provides a non-null value. When no chat exists, the resolver persists a new chat from remote data with explicit mapper defaults, including release notifications based on privacy.

## Goals / Non-Goals

**Goals:**

- Introduce a chat config domain dataclass, mapper, and repository that match the repository pattern used by newer persistence units.
- Keep `ChatConfigDB` as the only SQLAlchemy model for the existing `chat_configs` table.
- Preserve all current external API behavior and database schema behavior.
- Make creation defaults and remote-owned overrides explicit in code rather than relying on accidental DTO defaults.
- Add repository tests beside legacy CRUD tests, then migrate production callers through the new repository/domain boundary.
- Leave old CRUD/schema files in place until their remaining DB CRUD tests are intentionally retired.

**Non-Goals:**

- No database migration or schema change.
- No endpoint, payload, response, or OpenAPI contract change.
- No enum relocation in the first pass; `ChatConfigDB.ChatType`, `MediaMode`, and `ReleaseNotifications` remain where they are to avoid a whole-system enum migration.
- No immediate removal of `db/crud/chat_config.py` or `db/schema/chat_config.py`.

## Decisions

### 1. Keep One SQLAlchemy Model

`ChatConfigDB` remains the only DB model and table definition for `chat_configs`.

The new model introduced by this change is a feature-level domain dataclass, not a second SQLAlchemy model or table. The repository maps between the dataclass and `ChatConfigDB`.

**Rationale**: This matches `usage_record` and `purchase_record`: one DB model, one domain model, one mapper, one repository. A second DB model would create competing table definitions and migration risk without solving the persistence boundary problem.

**Alternative considered**: Create a parallel SQLAlchemy model. Rejected because it duplicates table ownership and makes Alembic behavior harder to reason about.

### 2. Use a Nullable Domain ID for Create Parity

The chat config domain dataclass may carry `chat_id: UUID | None = None` during create flows. The repository lets SQLAlchemy generate `chat_id` using the existing `ChatConfigDB.chat_id` default when no ID is present, then returns the persisted domain object with a concrete ID.

**Rationale**: `chat_configs` currently generates IDs in the DB model. Preserving that avoids changing identity ownership during this refactor. It also keeps the first milestone close to existing `ChatConfigSave` behavior while moving persistence behind a repository.

**Alternative considered**: Require callers to generate UUIDs before saving. Rejected for the first pass because it changes current object lifecycle semantics without a clear benefit.

### 3. Repository Saves Full Domain Objects and Remote Snapshots

The repository provides persistence operations:

- `get(chat_id) -> ChatConfig | None`
- `get_all(skip, limit) -> list[ChatConfig]`
- `get_by_external_identifiers(external_id, chat_type) -> ChatConfig | None`
- `save(chat_config: ChatConfig | ChatConfigRemoteData) -> ChatConfig`
- `delete(chat_id) -> ChatConfig | None`

`save(ChatConfig)` treats the domain object as a complete persisted object. If `chat_id` points at an existing row, the row is updated with all domain fields. If `chat_id` is absent or no row exists for it, a new row is inserted and SQLAlchemy generates the ID when needed.

`save(ChatConfigRemoteData)` treats the input as a remote/platform snapshot. The repository looks up by `(external_id, chat_type)`. If a row exists, mapper-owned merge logic applies only remote-owned updates. If no row exists, mapper-owned creation logic builds a full `ChatConfig` from the snapshot plus explicit defaults.

**Rationale**: The repository stays responsible for persistence orchestration while the mapper owns cross-shape conversion. Callers can save full domain objects when they own all fields, or save remote data when they only have a platform snapshot.

**Alternative considered**: Keep separate `create`, `update`, and `get_by_external_identifiers_or_create` methods. Rejected because it forced platform callers to duplicate the existing-vs-missing branch and made the new repo less aligned with the current `save` usage.

### 4. Resolve Platform Snapshots with Explicit Ownership

Telegram and WhatsApp chat config resolution should follow this shape after their migration milestone:

```
remote_data = ChatConfigRemoteData(
    external_id = snapshot.external_id,
    chat_type = snapshot.chat_type,
    title = snapshot.title,
    is_private = snapshot.is_private,
    language_iso_code = snapshot.language_iso_code,
)

return repo.save(remote_data)
```

For existing chats, `language_iso_code`, `language_name`, `reply_chance_percent`, `release_notifications`, and `media_mode` remain DB-owned. `title` and non-null `is_private` refresh from remote data. For new chats, `from_remote_data` uses explicit defaults: private defaults to `True`, release notifications are `major` for private chats and `none` for public chats, and media mode defaults to `photo`.

**Rationale**: The resolver stops mutating the incoming mapped object and instead sends a typed remote snapshot to the repository. The mapper makes field ownership clear in one conversion boundary.

**Alternative considered**: Keep mutating a `ChatConfigSave`-like object before saving. Rejected because the object still conflates partial platform snapshots with full persistence data.

### 5. Migrate Callers Through Domain Boundaries

The new repository is added to DI immediately but remains inert until a caller uses it. The original migration plan used small review gates:

1. Add domain/mapper/repo/DI and tests only.
2. Migrate `SettingsController` direct chat config reads/writes.
3. Migrate Telegram and WhatsApp chat config resolution.
4. Migrate lower-risk read paths such as announcements, SDK lookup code, and integration helpers.
5. Migrate `AuthorizationService` after the lower-risk paths have been reviewed.
6. Remove legacy DI access after production imports are gone.
7. Remove legacy CRUD/schema files only when their remaining tests are retired.

During implementation, review feedback broadened the migration to all domain-layer callers including authorization. The production boundary now uses `chat_config_repo` and the new domain `ChatConfig` across DI, settings, authorization, membership, platform resolvers, integrations, announcements, SDK lookup code, responders, and prompt-resolver paths.

**Rationale**: Once settings and repository behavior were reviewed, keeping mixed legacy/domain model types in the domain layer became more risky than migrating the rest of the domain boundary together. Removing `chat_config_crud` from DI prevents new production code from drifting back to the legacy path.

**Alternative considered**: Big-bang replace every `db.schema.chat_config` and `chat_config_crud` import. Rejected due to broad blast radius and poor reviewability.

## Risks / Trade-offs

- **Repository and CRUD temporarily coexist** -> Mitigation: keep both test suites green and remove CRUD only after `rg "chat_config_crud|db.schema.chat_config"` shows no production imports.
- **Partial migration causes mixed model types in callers** -> Mitigation: migrate one owner boundary at a time and adjust mocks/tests per milestone.
- **Existing resolver behavior changes accidentally** -> Mitigation: use Telegram/WhatsApp data resolver tests as canaries, especially existing-chat remote-field updates, DB-owned field preservation, and new-chat default tests.
- **Enum migration expands scope** -> Mitigation: do not move `ChatConfigDB` nested enums in this change.
- **Authorization regression** -> Mitigation: migrate `AuthorizationService` only after repository behavior is covered, then run authorization/settings tests and the full offline suite.

## Migration Plan

1. Add the new domain model, mapper, repository, DI property, and SQL test helper.
2. Add mapper and repository tests that mirror the existing CRUD behavior.
3. Migrate production callers through API/service boundaries, platform resolvers, integrations, announcements, SDK lookup code, responders, and authorization.
4. After each milestone, run the focused tests for the migrated boundary.
5. When all production callers use the repository, remove legacy DI access to `chat_config_crud`.
6. Remove legacy chat config CRUD/schema and their now-obsolete tests in a final cleanup after review.
7. Run the full offline test suite and pre-commit before closing implementation.

Rollback during the transition is straightforward because the database schema does not change and legacy CRUD remains available until the final removal milestone.

## Open Questions

None. `is_private` is intentionally treated as a remote-owned platform fact when the snapshot provides it.
