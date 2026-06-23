## Why

Chat-message persistence still uses the legacy `db/schema` and `db/crud` pattern, exposing Pydantic persistence schemas and SQLAlchemy rows throughout chat history, platform mapping, SDK sends, reactions, integrations, and cleanup. Its save schema also combines incomplete platform data with persistable state and uses an import-time `datetime.now()` default, making message state and update semantics ambiguous.

## What Changes

- Add feature-level chat-message domain, remote-data, mapper, and repository types while retaining `ChatMessageDB` as the only SQLAlchemy model.
- Represent platform-mapped messages without internal chat/author IDs separately from complete message domain state with a required `chat_id`.
- Correct omitted `sent_at` initialization to use construction time through a dataclass `default_factory` rather than process import time.
- Make remote-message merge behavior explicit: preserve composite identity, preserve an existing author when no new author resolves, and apply incoming timestamp and text for message edits.
- Standardize existing-row updates across message, attachment, chat-config, tools-cache, sponsorship, and price-alert persistence so feature mappers own field application and repositories own transaction orchestration.
- Preserve composite-key lookup, latest-message ordering and pagination, complete-state save, deletion, cleanup counts, platform sends, replies, reactions, chat history, and integration behavior.
- Migrate Telegram, WhatsApp, chat agent, platform integration, cleanup, DI, and test consumers in reviewable milestones.
- Remove the legacy message CRUD/schema layer only after all production and test references have migrated.

## Capabilities

### New Capabilities

- `chat-message-persistence`: Complete and remote message states, repository persistence, platform message merging, history queries, sends, reactions, and cleanup without legacy persistence schemas.

### Modified Capabilities

_(None.)_

## Impact

**Code**
- New message domain, remote-data, mapper, and repository modules under the chat feature.
- Existing persistence mappers gain a shared `apply_to_db_model(domain_model, db_model)` convention and their repositories remove private field-copy helpers.
- DI and `test/db/sql_util.py` gain repository access during staged migration and later remove message CRUD access.
- Chat agent, integrations, Telegram/WhatsApp mappers and resolvers, platform SDKs, responders, cleanup, and tests migrate to message domain models.

**Database**
- No table, column, key, constraint, default, encryption, or Alembic migration change is intended.
- `ChatMessageDB` remains the only SQLAlchemy representation with `(chat_id, message_id)` as its composite identity.

**API**
- No route, payload, platform API, LLM, notification, reaction, or OpenAPI behavior change is intended.

**Behavior**
- Domain messages created without `sent_at` receive their construction time instead of the legacy schema's process import time.

**Tests**
- Mapper and repository tests replace legacy schema/CRUD coverage, with snapshot-based assertions for exact replacement and remote merge semantics.
- Existing chat-agent, integrations, Telegram, WhatsApp, responder, SDK, attachment, and cleanup tests remain behavior canaries.
