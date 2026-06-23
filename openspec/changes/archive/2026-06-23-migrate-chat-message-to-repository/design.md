## Context

Chat messages currently use one Pydantic base, an incomplete `ChatMessageSave`, a persisted `ChatMessage`, and `ChatMessageCRUD`. Telegram and WhatsApp mappers create save objects before the internal chat UUID and author UUID are resolved. Their data resolvers mutate those objects, query SQLAlchemy rows, preserve selected fields for existing messages, and convert the saved row back to Pydantic.

The same legacy types cross chat-history loading, burst and mention detection, platform integration activity checks, platform SDK return values, outgoing message storage, reactions, and cleanup. `ChatMessageDB` already has the required persistence shape: `(chat_id, message_id)` is the composite primary key, `author_id` is nullable, `sent_at` and encrypted `text` are required, and attachment rows reference the same composite key.

The current `ChatMessageSave.sent_at = datetime.now()` is evaluated when the schema module is imported. Its update test also compares a SQLAlchemy object after in-place mutation, so it does not detect that omitted update fields replace the existing author and timestamp. The migration must distinguish complete replacement in the repository from deliberate remote merge behavior in platform resolvers.

The target flow is:

```
platform update
      │
      ▼
remote message data ───────┐
                           │ resolver supplies chat UUID
resolved author UUID ──────┤ and merges existing message state
existing domain message ───┤
                           ▼
                 complete message domain
                           │
                           ▼
                      repository
                           │
                           ▼
                    ChatMessageDB
```

## Goals / Non-Goals

**Goals:**

- Introduce message domain, remote-data, mapper, and repository modules under the chat feature.
- Make `chat_id` required in complete domain state and absent from pre-resolution platform data.
- Keep `author_id` out of remote message data because it is resolved through the separate user pipeline.
- Correct omitted domain timestamps to be generated at object construction time.
- Preserve platform message edits, author fallback, composite identity, encrypted text storage, history ordering, pagination, sends, replies, reactions, and cleanup.
- Migrate production consumers and tests in reviewable milestones before deleting legacy persistence types.

**Non-Goals:**

- No table, column, primary key, foreign key, unique constraint, encryption, server-default, or Alembic migration change.
- No user persistence, chat configuration persistence, or attachment persistence redesign.
- No platform API, message formatting, debounce, mention detection, reply quoting, reaction, LLM history, retention, or OpenAPI behavior redesign.
- No generated internal message ID; the existing `(chat_id, message_id)` identity remains authoritative.
- No partial-update repository API.

## Decisions

### 1. Keep One SQLAlchemy Model and Its Composite Identity

`ChatMessageDB` remains the only SQLAlchemy representation. The complete domain model uses the same required `chat_id` and `message_id` identity. Repository lookup, save, and deletion use both key components, and no generated identity is introduced.

**Rationale**: Platform message IDs are scoped by chat, and the database already enforces that identity through its primary and unique constraints.

**Alternative considered**: Add an internal generated message ID. Rejected because it changes the database and provides no capability needed by current consumers.

### 2. Model Remote and Complete Message States Separately

The feature defines:

```
ChatMessageRemoteData
    message_id: str
    sent_at: datetime
    text: str

ChatMessage
    chat_id: UUID
    message_id: str
    text: str
    author_id: UUID | None
    sent_at: datetime
```

Telegram and WhatsApp mappers return remote data without internal chat or author IDs. After chat and user resolution, the data resolver converts it into complete domain state or applies it to an existing domain message.

**Rationale**: `chat_id = None` is valid during platform mapping but invalid for persistence. The author UUID belongs to the separately resolved internal user, not the remote message payload.

**Alternative considered**: Keep `chat_id: UUID | None` on one domain model. Rejected because it preserves the current invalid intermediate state and requires late runtime validation before saving.

### 3. Keep Conversion and Remote Merge Rules in the Message Mapper

The mapper provides DB/domain conversion plus explicit `from_remote_data(remote_data, chat_id, author_id)` and `apply_remote_data(existing, remote_data, author_id)` functions.

For an existing message:

- Existing `chat_id` and `message_id` are preserved.
- A newly resolved non-null `author_id` replaces the existing author; otherwise the existing author is preserved.
- Incoming `sent_at` and `text` replace existing values, preserving Telegram and WhatsApp edit behavior.

**Rationale**: These are platform snapshot semantics, not persistence mechanics. They must happen before repository save and remain independently testable.

**Alternative considered**: Hide merge rules inside repository `save`. Rejected because pure complete-domain saves must replace supplied state exactly and must not depend on whether state originated remotely.

### 4. Repository Saves Only Complete Domain State

The repository exposes:

- `get(chat_id, message_id) -> ChatMessage | None`
- `get_all(skip, limit) -> list[ChatMessage]`
- `get_latest_by_chat(chat_id, skip, limit) -> list[ChatMessage]`
- `save(message) -> ChatMessage`
- `delete(chat_id, message_id) -> ChatMessage | None`
- `delete_older_than(cutoff) -> int`

Save queries by the composite key. Insert writes every domain field. Update preserves the composite identity and replaces `author_id`, `sent_at`, and `text` with supplied complete state. Every operation returns detached domain snapshots rather than SQLAlchemy rows.

**Rationale**: This matches established feature repository patterns and removes separate create/update surfaces without introducing patch semantics.

### 5. Generate Omitted Domain Timestamps at Construction Time

The complete domain model uses `sent_at: datetime = field(default_factory = datetime.now)`. Remote message data requires an explicit timestamp because both platform payloads provide one. The database `func.now()` default remains unchanged, while repository conversion normally supplies the domain timestamp explicitly.

**Rationale**: Construction-time generation matches the apparent intent of the legacy schema while removing its process-import-time bug.

**Alternative considered**: Preserve the static legacy default. Rejected because all objects omitting `sent_at` would share an unrelated process-start timestamp.

### 6. Use Complete Domain Messages Across Shared and Outgoing Boundaries

Chat history, integrations, `PlatformBotSDK`, Telegram and WhatsApp SDK returns, responder reactions, and cleanup use the complete domain type and repository. Telegram API send responses continue through its mapper/resolver pipeline. WhatsApp outgoing responses construct complete domain state after resolving the chat. `DomainLangchainMapper` returns complete messages because chat, agent, and timestamp are already known.

**Rationale**: One complete type across post-resolution boundaries removes SQLAlchemy/Pydantic conversions without adding a third outgoing draft state.

### 7. Verify Updates with Independent Snapshots

Repository tests capture pre-update domain values before saving replacement state. Tests explicitly verify exact replacement and remote merge behavior rather than comparing a mutable SQLAlchemy instance to itself.

**Rationale**: The legacy update test currently masks author and timestamp replacement because its original reference is mutated in place.

### 8. Migrate in Reviewable Milestones

The repository is introduced beside the CRUD. Read-only consumers migrate first, followed by platform mappers/resolvers, outgoing SDK and responder paths, cleanup, and finally legacy deletion. Each broad platform boundary ends with focused tests and manual review.

**Rationale**: Message persistence sits on every chat ingress and egress path, so staged replacement limits review scope and preserves rollback until the final deletion.

### 9. Persistence Mappers Apply Domain State to Existing Rows

Each persistence mapper exposes `apply_to_db_model(domain_model, db_model)`. The function mutates the existing SQLAlchemy row, applies every mutable persisted field, preserves the row's identity fields, and returns `None`. Repositories use it before commit and refresh instead of owning private field-copy helpers.

This convention applies consistently to chat messages, chat-message attachments, chat configurations, tools cache entries, sponsorships, and price alerts.

**Rationale**: Mappers already own field-level domain/database conversion. Repositories should orchestrate lookup and transaction behavior without duplicating persistence field knowledge.

**Alternative considered**: Reuse `db(domain_model)` for updates. Rejected because it creates a new transient SQLAlchemy object rather than updating the instance tracked by the session, risking identity conflicts or insert behavior.

## Risks / Trade-offs

- **Remote merge accidentally changes message-edit behavior** -> Test author fallback, incoming author replacement, timestamp replacement, text replacement, and stable composite identity for both platforms.
- **Complete save is mistaken for a partial update** -> Keep repository `save` limited to complete domain state and test exact replacement from independent snapshots.
- **Timestamp correction changes omitted-time behavior** -> Document the intentional correction and test that separately constructed messages receive construction-time values.
- **Latest-message ordering or pagination changes** -> Preserve descending `sent_at`, offset, and limit queries exactly and test multiple chats and boundary pages.
- **Mixed legacy/domain objects remain at shared boundaries** -> Retain CRUD/schema until project-wide production and test reference searches are clean.
- **Message deletion violates attachment foreign keys** -> Preserve cleanup ordering so attachments are deleted before parent messages; targeted deletion retains current database constraints.
- **Platform send or reaction persistence diverges** -> Keep existing SDK/resolver paths and use responder/SDK behavior tests as migration canaries.
- **Mapper application omits a mutable field or changes identity** -> Test every mapper's application function directly, including identity preservation and nullable field clearing.

## Migration Plan

1. Add complete and remote message models, mapper, repository, DI property, SQL test helper, and focused tests beside the CRUD.
2. Review state boundaries, timestamp generation, merge rules, composite identity, save semantics, ordering, and cleanup behavior.
3. Migrate read-only chat agent and integration consumers to domain repository results.
4. Migrate Telegram and WhatsApp platform mappers and data resolvers to remote conversion and explicit merge behavior.
5. Migrate shared SDK return boundaries, outgoing message storage, LangChain storage mapping, reactions, responders, and tests.
6. Migrate cleanup to repository deletion and run broad message, attachment, platform, and integration tests.
7. Remove legacy DI access, CRUD/schema files, SQL helper, and obsolete tests after reference searches are clean.
8. Run the full offline suite, all-files pre-commit, and strict OpenSpec validation.

Rollback remains straightforward before legacy deletion because both persistence paths target the unchanged table. After deletion, reverting the migration restores the legacy files without a data migration.

## Open Questions

None. The timestamp correction is intentional, remote data excludes internal IDs, and complete repository saves replace supplied state exactly.
