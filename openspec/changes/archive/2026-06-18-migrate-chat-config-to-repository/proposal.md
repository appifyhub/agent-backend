## Why

Chat config persistence still uses the legacy `db/schema` + `db/crud` pattern, which leaks SQLAlchemy/Pydantic persistence types into API controllers, authorization, and platform data resolvers. Newer persistence areas such as usage records and chat memberships use feature-level domain dataclasses, explicit DB/domain mappers, and repositories, making persistence behavior easier to test and refactor safely.

## What Changes

- Add a feature-level chat config domain model, mapper, and repository beside the existing `ChatConfigDB` SQLAlchemy model.
- Keep `ChatConfigDB` as the single database model and preserve the existing `chat_configs` table, columns, indexes, defaults, and uniqueness behavior.
- Add the new repository to DI immediately, then remove DI access to the legacy CRUD after production callers are migrated.
- Preserve current chat config behavior while migrating callers gradually:
  - direct domain saves persist the full chat config object;
  - remote/platform snapshot saves update only remote-owned fields for existing chats;
  - newly discovered remote/platform chats receive explicit defaults in the mapper.
- Migrate production callers from API/service boundaries through platform resolvers, integrations, announcements, SDK lookup code, and authorization.
- Keep legacy CRUD tests until the CRUD file is no longer used by production code; add repository/mapper tests first and maintain both test sets during the transition.

## Capabilities

### New Capabilities

- `chat-config-persistence`: Domain-model and repository behavior for creating, reading, updating, and resolving chat configurations without exposing SQLAlchemy DB models or legacy Pydantic persistence schemas to callers.

### Modified Capabilities

_(None — no existing chat config persistence spec.)_

## Impact

**Code**
- New feature-level chat config files under `src/features/chat/config/` or an equivalent feature-local package.
- `src/di/di.py` gains `chat_config_repo`; `chat_config_crud` is removed from DI once production callers no longer use it.
- `test/db/sql_util.py` gains a `chat_config_repo()` helper for focused repository tests.
- Production callers are migrated from legacy CRUD/schema use to the new repository/domain model.

**Database**
- No table, column, index, enum, or migration changes are intended.
- `src/db/model/chat_config.py` remains the only SQLAlchemy representation for `chat_configs`.

**API**
- No external API route, payload, response, or OpenAPI behavior changes are intended.
- Settings endpoints should continue returning the same externally visible data while their internal persistence dependency changes.

**Tests**
- New mapper tests verify DB/domain round trips, remote snapshot conversion, merge behavior, enum fields, generated-ID create behavior, and `None` handling.
- New repository tests mirror existing `test/db/crud/test_chat_config.py` behavior and cover `ChatConfigRemoteData` save semantics.
- Existing settings, authorization, Telegram, WhatsApp, integration, announcement, SDK, and responder tests remain behavior canaries through migration.
