## Why

Price-alert persistence still uses the legacy `db/schema` + `db/crud` pattern, exposing Pydantic persistence schemas and SQLAlchemy rows to the currency-alert service and cleanup flow. Migrating it now extends the repository/domain pattern already established for chat configs, sponsorships, and tools cache while correcting the import-time `last_price_time` default.

## What Changes

- Add a feature-level price-alert domain dataclass, mapper, and repository beside the existing `PriceAlertDB` SQLAlchemy model.
- Preserve the existing composite identity `(chat_id, base_currency, desired_currency)`, complete alert state, full upsert behavior, chat-scoped queries, deletion, and stale-alert cleanup.
- Default `last_price_time` per domain instance instead of once when the legacy Pydantic schema module is imported.
- Add the repository to DI and the SQL test helper while keeping the legacy CRUD available during staged migration.
- Migrate `CurrencyAlertService`, `CleanupService`, and their tests to repository domain models.
- Remove legacy `price_alert_crud`, `db.schema.price_alert`, and obsolete CRUD/schema tests only after all consumers have migrated.
- Keep the direct `PriceAlertDB.owner_id` bulk update in `ProfileConnectService` unchanged because it participates in an existing cross-model transaction and does not use the legacy CRUD.

## Capabilities

### New Capabilities

- `price-alert-persistence`: Domain-model and repository behavior for composite alert identity, complete-state upsert, lookup, deletion, stale cleanup, and per-instance price timestamps without exposing legacy persistence schemas.

### Modified Capabilities

_(None.)_

## Impact

**Code**
- New price-alert domain, mapper, and repository files under `src/features/currencies/`.
- `src/di/di.py` gains `price_alert_repo`; `price_alert_crud` is removed after callers migrate.
- `CurrencyAlertService` and `CleanupService` consume repository domain models.
- `test/db/sql_util.py` gains a repository helper and later removes its CRUD helper.

**Database**
- No table, column, composite primary key, foreign key, nullability, or migration changes are intended.
- `src/db/model/price_alert.py` remains the only SQLAlchemy representation for `price_alerts`.

**API**
- No route, payload, response, LLM-tool, notification, or OpenAPI behavior changes are intended.

**Tests**
- New mapper and repository tests replace legacy schema/CRUD coverage.
- Existing currency-alert, cleanup, responder, profile-connect, and integration tests remain behavior canaries.
