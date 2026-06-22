## Why

Chat-message attachment persistence still uses the legacy `db/schema` + `db/crud` pattern, which exposes Pydantic persistence schemas and SQLAlchemy rows throughout platform mapping, resolution, SDK refresh, chat processing, and cleanup flows. The current `ChatMessageAttachmentSave` also represents both incomplete platform data and persistable state, allowing `chat_id = None` even though the database requires it.

## What Changes

- Add feature-level chat-message attachment domain, remote-data, mapper, and repository types while retaining `ChatMessageAttachmentDB` as the only SQLAlchemy model.
- Represent platform-mapped attachment data without internal attachment/chat IDs separately from complete attachment domain state with a required `chat_id`.
- Match ChatConfig ID handling: allow an unsaved domain attachment to omit `id`, generate the short ID through a client-side SQLAlchemy default, and return the generated ID after persistence; centrally derive deterministic platform attachment IDs from remote external IDs.
- Preserve attachment lookup, complete-state save, deletion, message-scoped queries, stale-data detection, remote metadata merging, URL refresh, media-type detection, and old-message cleanup behavior.
- Migrate Telegram, WhatsApp, platform integration, chat processing, attachment utility, chat-agent, image-editing, URL-resolution, cleanup, DI, and test consumers in reviewable milestones.
- Remove the legacy attachment CRUD/schema layer only after all production and test references have migrated.

## Capabilities

### New Capabilities

- `chat-message-attachment-persistence`: Domain and remote attachment states, ChatConfig-style ID generation, repository persistence, platform metadata merging, refresh behavior, and old-message cleanup without legacy persistence schemas.

### Modified Capabilities

_(None.)_

## Impact

**Code**
- New attachment domain, remote-data, mapper, and repository modules under the chat feature.
- DI and `test/db/sql_util.py` gain repository access during staged migration and later remove attachment CRUD access.
- Telegram/WhatsApp mappers, resolvers, SDKs, platform integration, chat consumers, and cleanup migrate to attachment domain models.

**Database**
- No table, column, foreign key, index, nullability, or migration change is intended.
- `ChatMessageAttachmentDB` remains the only SQLAlchemy representation; its ID receives a Python-side default equivalent to current CRUD generation.

**API**
- No route, payload, LLM-tool, media-processing, notification, or OpenAPI behavior change is intended.

**Tests**
- Mapper and repository tests replace legacy schema/CRUD coverage.
- Existing platform mapper/resolver, SDK, attachment processor, chat agent, image edit, cleanup, and integration tests remain behavior canaries.
