## Why

User persistence still uses the legacy `db/schema` + `db/crud` pattern, which exposes Pydantic persistence schemas and SQLAlchemy rows across authorization, settings, platform resolvers, sponsorships, accounting, profile connection, integrations, and tests. It also uses one `UserSave` shape for both complete user state and partial remote platform snapshots, forcing Telegram and WhatsApp resolvers to preserve DB-owned fields manually.

## What Changes

- Add feature-level user domain, remote-data, mapper, and repository types while retaining `UserDB` as the only SQLAlchemy model for the existing `simulants` table.
- Mirror the chat-config remote-data mapper pattern:
  - complete `User` domain saves persist full user state;
  - `UserRemoteData` lookups use platform identifiers and merge only platform-owned fields for existing users;
  - new remote users receive explicit onboarding defaults before mapper-owned conversion to complete user state.
- Keep secret fields represented as `SecretStr` in the domain and converted to plain encrypted-string values only at the DB mapper boundary.
- Preserve current connect-key generation, created-at persistence, waitlist/capacity behavior, policy flags, groups, API keys, tool choices, credit balances, lookup methods, deletion behavior, and locked accounting updates.
- Add repository and mapper tests beside the legacy CRUD tests before migrating production callers.
- Migrate production callers in reviewable milestones, with platform user resolution and settings writes handled before broader accounting/profile-connection cleanup.
- Remove legacy user CRUD/schema files only after production and test references are gone.

## Capabilities

### New Capabilities

- `user-persistence`: Domain-model and repository behavior for creating, reading, updating, resolving remote platform users, locked credit updates, and deleting users without exposing SQLAlchemy rows or legacy Pydantic persistence schemas to callers.

### Modified Capabilities

_(None — no existing user persistence spec.)_

## Impact

**Code**
- New user domain, remote-data, mapper, and repository modules under a feature-level user package.
- `src/di/di.py` gains `user_repo`; `user_crud` stays during migration and is removed after production callers no longer use it.
- `test/db/sql_util.py` gains a `user_repo()` helper for focused repository tests.
- Telegram and WhatsApp domain/data resolvers migrate from `UserSave` to `UserRemoteData` and explicit mapper merge behavior.
- Authorization, settings, integrations, sponsorships, accounting, profile connection, chat membership, prompt resolution, and support paths migrate from legacy user schemas to the new domain model in staged steps.

**Database**
- No table, column, index, unique constraint, enum, encrypted column, default, or Alembic migration change is intended.
- `src/db/model/user.py` remains the only SQLAlchemy representation for the `simulants` table.

**API**
- No route, payload, response, JWT, settings, sponsorship, purchase, transfer, or OpenAPI behavior change is intended.

**Behavior**
- Remote platform user snapshots become explicit partial inputs instead of incomplete full persistence DTOs.
- Existing user-owned settings, secrets, credits, onboarding flags, group, and connect key remain preserved when Telegram or WhatsApp sends new platform data.

**Tests**
- New mapper tests verify DB/domain conversion, secret conversion, remote creation, remote merge field ownership, connect-key handling, and existing-row application.
- New repository tests mirror existing user CRUD behavior and cover locked single-user and paired-user updates.
- Existing platform resolver, settings, authorization, sponsorship, accounting, profile-connect, integration, prompt, and support tests remain behavior canaries through migration.
