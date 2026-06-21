## Why

Tools cache persistence still uses the legacy `db/schema` + `db/crud` pattern, which exposes Pydantic persistence schemas and SQLAlchemy rows to cache consumers across chat, currencies, web browsing, cleanup, and tests. The completed sponsorship migration provides a proven repository/domain pattern that can remove this leakage while preserving cache behavior.

## What Changes

- Add a feature-level tools cache domain dataclass, mapper, and repository beside the existing `ToolsCacheDB` SQLAlchemy model.
- Keep `ToolsCacheDB` as the single database model and preserve the existing `tools_cache` table, string primary key, stored value, nullable expiration timestamp, and deterministic key format.
- Move cache-entry behavior to the domain boundary:
  - `created_at` defaults per instance instead of at Python module import time;
  - `expires_at = None` continues to mean the entry never expires;
  - expiration checks and deterministic key creation remain available without exposing persistence types.
- Add the new repository to DI, migrate cache consumers in bounded feature groups, then remove legacy `tools_cache_crud` / `db.schema.tools_cache` access after callers and tests are migrated.
- Preserve current cache hit/miss, full upsert, explicit expiration, expired-entry cleanup, and deletion behavior.
- Keep legacy CRUD/schema tests until equivalent domain, mapper, and repository coverage is accepted.

## Capabilities

### New Capabilities

- `tools-cache-persistence`: Domain-model and repository behavior for deterministic cache keys, cache-entry expiration, full create/update persistence, lookup, deletion, and expired-entry cleanup without exposing SQLAlchemy models or legacy Pydantic persistence schemas.

### Modified Capabilities

_(None.)_

## Impact

**Code**
- New feature-level tools cache files under `src/features/tools_cache/` or an equivalent feature-local package.
- `src/di/di.py` gains `tools_cache_repo`; `tools_cache_crud` is removed after production callers no longer use it.
- Cache consumers in chat attachments, currencies, web browsing, Twitter fetching, HTML cleanup, and cleanup migrate to repository domain models.
- `test/db/sql_util.py` gains a `tools_cache_repo()` helper for focused repository tests.

**Database**
- No table, column, primary key, nullability, or migration changes are intended.
- `src/db/model/tools_cache.py` remains the only SQLAlchemy representation for `tools_cache`.

**API**
- No external route, payload, response, or OpenAPI behavior changes are intended.

**Tests**
- New domain/mapper tests cover per-instance creation timestamps, nullable expiration, expiration checks, deterministic key compatibility, and DB/domain round trips.
- New repository tests replace legacy CRUD coverage for create, get, list, full upsert, delete, and expired-entry cleanup behavior.
- Existing consumer tests remain behavior canaries while each feature group migrates.
