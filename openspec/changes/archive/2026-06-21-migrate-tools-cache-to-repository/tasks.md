## 1. Repository Foundation

- [x] 1.1 Create the feature-level `src/features/tools_cache/` package and `ToolsCache` domain dataclass while leaving `ToolsCacheDB` as the only SQLAlchemy model.
- [x] 1.2 Move `is_expired()` and deterministic `create_key()` behavior to the domain model while preserving the existing key algorithm and golden output.
- [x] 1.3 Implement per-instance `created_at` defaulting with `field(default_factory = datetime.now)` and preserve `expires_at = None` as never-expiring state.
- [x] 1.4 Create `tools_cache_mapper.py` with DB-to-domain and domain-to-DB conversion covering key, value, creation timestamp, and nullable expiration.
- [x] 1.5 Create `ToolsCacheRepository` with `get`, `get_all`, `save`, `delete`, and `delete_expired`.
- [x] 1.6 Ensure repository `save` performs exact full-object insert/update and can persist `expires_at = None`.
- [x] 1.7 Wire `tools_cache_repo` into `src/di/di.py` without removing `tools_cache_crud`.
- [x] 1.8 Add `tools_cache_repo()` to `test/db/sql_util.py`.
- [x] 1.9 Add domain tests covering per-instance timestamps, never/future/past expiration, deterministic keys, and golden key compatibility.
- [x] 1.10 Add mapper tests covering DB/domain round trips and nullable expiration.
- [x] 1.11 Add repository tests mirroring legacy get/list/upsert/delete/cleanup behavior, including timestamp replacement and clearing expiration.
- [x] 1.12 Run focused domain, mapper, repository, legacy CRUD, and legacy schema tests.
- [x] 1.13 Stop for manual review of the domain and repository shape before migrating production consumers.

## 2. Currency Cache Migration

- [x] 2.1 Migrate `ExchangeRateFetcher` key creation, lookup, expiration checks, and writes to the domain model and `tools_cache_repo`.
- [x] 2.2 Remove currency-layer `db.schema.tools_cache`, `ToolsCacheSave`, and `ToolsCache.model_validate(...)` usage.
- [x] 2.3 Update exchange-rate fetcher tests and mocks to use `ToolsCacheRepository` and tools cache domain models.
- [x] 2.4 Verify direct, inverse, expired, missing, fiat, and crypto cache behavior remains unchanged.
- [x] 2.5 Run focused currency and dependent currency-alert tests.
- [x] 2.6 Stop for manual review of currency cache behavior.

## 3. Web-Browsing Cache Migration

- [x] 3.1 Migrate `HTMLContentCleaner` key creation, lookup, expiration checks, and writes to the domain model and repository.
- [x] 3.2 Migrate `WebFetcher` key creation, HTML/JSON lookups, expiration checks, and writes to the domain model and repository.
- [x] 3.3 Migrate `TwitterStatusFetcher` text/structured key creation, lookups, expiration checks, and writes to the domain model and repository.
- [x] 3.4 Remove web-browsing `db.schema.tools_cache`, `ToolsCacheSave`, and `ToolsCache.model_validate(...)` usage.
- [x] 3.5 Update HTML cleaner, web fetcher, and Twitter fetcher tests/mocks to return tools cache domain models instead of Pydantic models or dictionaries.
- [x] 3.6 Verify HTML, JSON, tweet text, structured tweet, expired, missing, and refresh behavior remains unchanged.
- [x] 3.7 Run focused web-browsing cache consumer tests.
- [x] 3.8 Stop for manual review of web-browsing cache behavior.

## 4. Chat and Cleanup Migration

- [x] 4.1 Migrate `ChatAttachmentProcessor` key creation, cache lookup, expiration checks, and writes to the domain model and repository.
- [x] 4.2 Remove chat attachment `db.schema.tools_cache`, `ToolsCacheSave`, and `ToolsCache.model_validate(...)` usage.
- [x] 4.3 Migrate scheduled expired-cache deletion in `CleanupService` to `tools_cache_repo.delete_expired()`.
- [x] 4.4 Update chat attachment, cleanup, currency-alert service/responder, and other support tests/mocks that reference `tools_cache_crud` or `ToolsCacheCRUD`.
- [x] 4.5 Verify document and non-document attachment caching, error handling, cleanup counts, and responder behavior remain unchanged.
- [x] 4.6 Run focused chat attachment, cleanup, currency-alert, and responder tests.
- [x] 4.7 Stop for manual review before legacy cleanup.

## 5. Legacy Cleanup

- [x] 5.1 Search production and test code for `tools_cache_crud`, `ToolsCacheCRUD`, `db.schema.tools_cache`, `ToolsCacheSave`, and `ToolsCache.model_validate`.
- [x] 5.2 Remove legacy `tools_cache_crud` access from DI after production callers are migrated.
- [x] 5.3 Replace the legacy schema expiration tests with accepted domain-model coverage.
- [x] 5.4 Remove obsolete legacy tools cache CRUD/schema tests after repository/domain coverage is accepted.
- [x] 5.5 Remove `src/db/crud/tools_cache.py`, `src/db/schema/tools_cache.py`, and `SQLUtil.tools_cache_crud()` after no production or test references remain.
- [x] 5.6 Confirm no production or test references to legacy tools cache CRUD/schema types remain.
- [x] 5.7 Stop for manual review before final verification.

## 6. Final Verification

- [x] 6.1 Run `pipenv run pytest`.
- [x] 6.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 6.3 Confirm no database migration was generated or required for this change.
- [x] 6.4 Confirm no external API/OpenAPI behavior changed.
- [x] 6.5 Validate the OpenSpec change with `openspec validate migrate-tools-cache-to-repository --strict`.
- [x] 6.6 Summarize the deliberate `created_at` correction, remaining risks, and completion status for final review.
