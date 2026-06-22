## Context

Chat-message attachments currently use one Pydantic base, an incomplete `ChatMessageAttachmentSave`, a persisted `ChatMessageAttachment`, and `ChatMessageAttachmentCRUD`. Platform mappers create save objects with deterministic IDs, external IDs, message IDs, and partial metadata before the internal chat UUID exists. Telegram and WhatsApp data resolvers save the chat configuration, assign its generated UUID to mapped attachments, preserve selected existing attachment data, and pass the mutable save object into platform SDK refresh logic.

The same legacy types then cross platform SDKs, chat attachment utilities, chat processing, image editing, chat history collection, URL resolution, platform integration, and cleanup. The database already has the required shape: a string primary key, a required `(chat_id, message_id)` foreign key, and nullable external/cache metadata. There are no direct attachment-table transactions outside the CRUD that require special unit-of-work handling.

The target pattern is:

```
platform update
      │
      ▼
remote attachment data ──┐
                         │ resolver supplies persisted chat UUID
existing domain data ────┤ and preserves existing cache state
                         ▼
              complete attachment domain
                         │
                         ▼
platform refresh ──▶ repository ──▶ ChatMessageAttachmentDB
```

## Goals / Non-Goals

**Goals:**

- Introduce attachment domain, remote-data, mapper, and repository modules under the chat feature.
- Make `chat_id` required in complete domain state while keeping it absent from pre-resolution platform data.
- Match ChatConfig ID lifecycle: optional unsaved domain ID, Python-side SQLAlchemy generation, and populated persisted return values.
- Preserve deterministic platform IDs, nullable metadata, stale-data behavior, merge rules, refresh behavior, queries, deletion, and old-message cleanup.
- Migrate production consumers and tests in reviewable milestones before deleting legacy persistence types.

**Non-Goals:**

- No table, column, foreign key, index, nullability, server-default, or Alembic migration change.
- No attachment URL lifetime, media download, upload, MIME detection, platform API, LLM-tool, or OpenAPI redesign.
- No uniqueness constraint for `external_id` and no change to first-match lookup behavior.
- No chat-message CRUD migration.
- No cleanup ordering change between attachment deletion and message deletion.

## Decisions

### 1. Keep One SQLAlchemy Model and Move ID Generation to Its Python Default

`ChatMessageAttachmentDB` remains the only SQLAlchemy model. Its `id` column receives `default = generate_short_uuid`, equivalent to the existing CRUD fallback but following `ChatConfigDB.chat_id` ownership of generated identity.

The domain model uses `id: str | None = None`. Repository save looks up an existing row only when an ID is present; otherwise it inserts and returns the generated ID after commit/refresh. The existing `generate_deterministic_short_uuid` utility derives deterministic platform IDs from remote `external_id` values, so platform identity remains unchanged without placing internal identity in remote data.

**Rationale**: Identity generation belongs to persistence for generic unsaved objects, while platform-derived deterministic identity remains explicit at the mapper boundary.

**Alternative considered**: Generate IDs with a domain `default_factory`. Rejected because it diverges from ChatConfig ID management and assigns persistence identity before save.

### 2. Model Remote and Complete States Separately

The feature defines:

```
ChatMessageAttachmentRemoteData
    external_id: str
    message_id: str
    nullable platform/cache metadata

ChatMessageAttachment
    id: str | None
    chat_id: UUID                 # required
    message_id: str
    external_id and cache metadata
    has_stale_data
```

Platform mappers return remote data without `chat_id`. After `ChatConfigRepository.save()` returns the internal UUID, the resolver converts remote data into complete domain state or applies it to an existing domain attachment.

**Rationale**: `chat_id = None` is valid only during mapping and is invalid for persistence. Separate types prevent incomplete attachment state from flowing into the repository or SDK refresh APIs.

**Alternative considered**: Keep `chat_id: UUID | None` on one domain model. Rejected because it preserves the current ambiguity and shifts failure to database insertion.

### 3. Keep Conversion and Remote Merge Rules in the Attachment Mapper

The mapper provides DB/domain conversion plus explicit `from_remote_data(remote_data, chat_id)` and `apply_remote_data(existing, remote_data)` functions. Both platform message-text formatting and new-domain conversion call the existing deterministic UUID utility directly.

For an existing external ID:

- Existing `id` and `chat_id` are preserved.
- Incoming `external_id` and `message_id` are applied.
- Incoming `size`, `last_url`, `last_url_until`, `extension`, and `mime_type` replace existing values only when truthy; otherwise existing values remain.

**Rationale**: These rules exactly match both current data resolvers. Keeping them in one mapper removes duplicated mutation while avoiding accidental conversion from truthy fallback to `None`-only semantics.

**Alternative considered**: Hide remote merging inside repository `save`. Rejected because the resolver must obtain complete merged state before platform refresh, and remote semantics are not persistence mechanics.

### 4. Repository Saves Only Complete Domain State

The repository exposes:

- `get(attachment_id) -> ChatMessageAttachment | None`
- `get_by_external_id(external_id) -> ChatMessageAttachment | None`
- `get_all(skip, limit) -> list[ChatMessageAttachment]`
- `get_all_by_message(chat_id, message_id) -> list[ChatMessageAttachment]`
- `save(attachment) -> ChatMessageAttachment`
- `delete(attachment_id) -> ChatMessageAttachment | None`
- `delete_by_old_messages(cutoff) -> int`

Insert writes every domain field. Update locates by non-null `id`, preserves that identity, and replaces every other persisted field. External-ID lookup keeps current `.first()` behavior because the index is not unique.

**Rationale**: The surface mirrors required production behavior without retaining separate create/update methods or accepting incomplete data.

### 5. Platform SDK Refresh Accepts One Complete Domain Object

Telegram and WhatsApp `refresh_attachment` methods accept only `ChatMessageAttachment`. Data resolvers perform remote conversion/merge first. SDK metadata changes use `dataclasses.replace`, and persistence uses the repository directly.

WhatsApp upload/re-upload helpers also return complete domain state and save through the repository. Existing batch refresh methods remain as public conveniences but retrieve domain objects directly.

**Rationale**: The current optional `attachment`/`attachment_save` signature encodes two states and permits calls with neither. One complete input removes that ambiguity and the repeated Pydantic model round trips.

**Alternative considered**: Retain both optional parameters using dataclasses. Rejected because remote data is resolved before SDK refresh and no production caller still needs an incomplete input.

### 6. Preserve Stale Detection and Cleanup Queries

`has_stale_data` moves unchanged to the complete domain model. `delete_by_old_messages` retains the existing subquery over `ChatMessageDB.sent_at < cutoff`, tuple membership on `(chat_id, message_id)`, commit behavior, and deleted-row count. Cleanup continues deleting attachments before messages.

**Rationale**: These behaviors are domain/repository responsibilities and already have externally relevant consequences.

### 7. Migrate in Reviewable Milestones

The repository is introduced beside the CRUD. Read-only consumers migrate first, followed by platform mappers/resolvers, Telegram SDK refresh, WhatsApp SDK refresh, cleanup, and finally legacy deletion. Each high-risk boundary ends with focused tests and manual review.

**Rationale**: Platform refresh behavior has a wider blast radius than the persistence mechanics and should be reviewed independently.

## Risks / Trade-offs

- **Generated ID timing moves from CRUD mutation to SQLAlchemy flush** -> Return only the committed/refreshed domain snapshot and test omitted-ID insertion plus deterministic-ID preservation.
- **Remote merge accidentally clears or overwrites cached metadata** -> Encode and test the current truthy fallback field by field.
- **Existing attachment is moved to a different chat** -> Preserve existing `chat_id` during remote merge exactly as today.
- **Dataclass replacement changes refresh outcomes** -> Test fresh, stale, missing external ID, API refresh, MIME/extension detection, and WhatsApp re-upload paths before removing schemas.
- **Broad consumer migration leaves mixed DB/schema types** -> Keep CRUD/schema available until project-wide reference searches are clean.
- **External IDs are assumed unique by callers but not constrained** -> Preserve current first-match behavior; uniqueness redesign remains out of scope.
- **Optional domain ID can escape before persistence** -> Platform conversion derives deterministic IDs from external IDs, while generic callers receive the generated ID from repository save, matching ChatConfig conventions.

## Migration Plan

1. Add domain, remote-data, mapper, repository, Python-side DB ID default, DI property, SQL test helper, and focused tests beside the CRUD.
2. Review complete/remote state boundaries, ID generation, save semantics, stale detection, and remote merge behavior.
3. Migrate read-only chat consumers and platform integration type boundaries to domain attachments.
4. Migrate Telegram and WhatsApp mappers/resolvers to remote data and complete-domain conversion.
5. Migrate Telegram SDK refresh paths and tests, then stop for review.
6. Migrate WhatsApp SDK upload/refresh paths and tests, then stop for review.
7. Migrate cleanup to repository deletion and run broad attachment/platform behavior tests.
8. Remove legacy DI access, CRUD/schema files, SQL helper, and obsolete tests after reference searches are clean.
9. Run the full offline suite, all-files pre-commit, and strict OpenSpec validation.

Rollback remains straightforward before legacy deletion because both persistence paths target the unchanged table. After deletion, reverting the migration restores the legacy files without data migration.

## Open Questions

None. Internal attachment/chat IDs are absent from remote data, deterministic platform IDs are centrally derived from external IDs, and all persisted attachment state is complete.
