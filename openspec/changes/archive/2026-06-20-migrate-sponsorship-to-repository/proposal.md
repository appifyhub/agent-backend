## Why

Sponsorship persistence still uses the legacy `db/schema` + `db/crud` pattern, which leaks SQLAlchemy/Pydantic persistence types into controllers, services, cleanup, transfer validation, and tests. After the chat config repository migration, sponsorships are a good next candidate because the domain is small, internal-only, and has clear state transitions.

## What Changes

- Add a feature-level sponsorship domain model, mapper, and repository beside the existing `SponsorshipDB` SQLAlchemy model.
- Keep `SponsorshipDB` as the single database model and preserve the existing `sponsorships` table, composite primary key, foreign keys, nullable `accepted_at`, and `sponsored_at` database default as a fallback.
- Model sponsorship state explicitly as a domain dataclass:
  - `sponsor_id` and `receiver_id` are always required;
  - `sponsored_at` defaults to the current application time and is non-null in domain code;
  - `accepted_at` remains intentionally nullable and is written exactly as domain state.
- Add the new repository to DI, migrate production callers from `sponsorship_crud` / `db.schema.sponsorship`, then remove legacy CRUD/schema access after callers and tests are migrated.
- Preserve current sponsorship behavior for sponsoring, accepting, unsponsoring, fetch responses, sponsored-user transfer restrictions, stale cleanup, and settings/sponsorship checks.
- Keep legacy CRUD tests until repository behavior is covered and production callers are migrated.

## Capabilities

### New Capabilities

- `sponsorship-persistence`: Domain-model and repository behavior for creating, reading, updating, deleting, accepting, and cleaning up sponsorships without exposing SQLAlchemy DB models or legacy Pydantic persistence schemas to callers.

### Modified Capabilities

_(None — no existing sponsorship persistence spec.)_

## Impact

**Code**
- New feature-level sponsorship files under `src/features/sponsorships/` or an equivalent feature-local package.
- `src/di/di.py` gains `sponsorship_repo`; `sponsorship_crud` is removed from DI once production callers no longer use it.
- `test/db/sql_util.py` gains a `sponsorship_repo()` helper for focused repository tests.
- Production callers are migrated from legacy CRUD/schema use to the new repository/domain model.

**Database**
- No table, column, primary key, foreign key, default, or migration changes are intended.
- `src/db/model/sponsorship.py` remains the only SQLAlchemy representation for `sponsorships`.

**API**
- No external API route, payload, response, or OpenAPI behavior changes are intended.
- Sponsorship endpoints should continue returning the same externally visible data while their internal persistence dependency changes.

**Tests**
- New mapper tests verify DB/domain round trips, `sponsored_at` domain default behavior, nullable `accepted_at` handling, and composite-key identity.
- New repository tests mirror existing `test/db/crud/test_sponsorship.py` behavior and cover create/update/save/delete/bulk cleanup semantics.
- Existing sponsorship controller/service, settings, transfer, cleanup, and responder tests remain behavior canaries through migration.
