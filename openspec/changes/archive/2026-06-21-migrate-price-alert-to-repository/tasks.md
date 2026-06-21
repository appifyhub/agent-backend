## 1. Repository Foundation

- [x] 1.1 Create `src/features/currencies/price_alert.py` with one complete `PriceAlert` domain dataclass while keeping `PriceAlertDB` as the only SQLAlchemy model.
- [x] 1.2 Preserve the required composite identity and complete owner, threshold, price, and timestamp state on the domain model.
- [x] 1.3 Implement `last_price_time` with `field(default_factory = datetime.now)` so omitted timestamps default independently per instance.
- [x] 1.4 Create `price_alert_mapper.py` with DB-to-domain and domain-to-DB conversion for every persisted field.
- [x] 1.5 Create `PriceAlertRepository` with `get`, `get_all`, `get_all_by_chat`, `save`, `delete`, and `delete_stale`.
- [x] 1.6 Ensure repository `save` inserts complete state and exactly replaces owner, threshold, last price, and last price timestamp for an existing composite identity.
- [x] 1.7 Preserve the strict `last_price_time < cutoff` stale-deletion predicate and deleted-row count.
- [x] 1.8 Wire `price_alert_repo` into `src/di/di.py` without removing `price_alert_crud`.
- [x] 1.9 Add `price_alert_repo()` to `test/db/sql_util.py` while retaining the CRUD helper.
- [x] 1.10 Confirm the domain timestamp uses `field(default_factory = datetime.now)` without adding tests for standard dataclass behavior.
- [x] 1.11 Add mapper tests covering complete DB/domain round trips.
- [x] 1.12 Add repository tests covering composite identity, missing lookup, all/chat-scoped queries, pagination, insert, exact update, deletion, and stale cleanup.
- [x] 1.13 Run focused mapper, repository, legacy CRUD, and legacy schema tests.
- [x] 1.14 Stop for manual review of the domain, composite identity, timestamp default, and repository surface.

## 2. Currency Alert Service Migration

- [x] 2.1 Migrate `CurrencyAlertService` imports and persistence access from legacy price-alert schemas/CRUD to `PriceAlert` and `price_alert_repo`.
- [x] 2.2 Keep repository domain objects inside service logic and map them to existing `ActiveAlert` and `TriggeredAlert` response models only at public boundaries.
- [x] 2.3 Migrate alert creation, listing, chat-scoped listing, and deletion while preserving response values and timestamp formatting.
- [x] 2.4 Migrate triggered-alert refreshes to `dataclasses.replace` so only last price and last price timestamp change before repository save.
- [x] 2.5 Update currency-alert service tests and mocks to use `PriceAlertRepository` and price-alert domain models.
- [x] 2.6 Add or refine tests proving refresh preserves identity, owner, and threshold while replacing price state.
- [x] 2.7 Verify zero-price, threshold, rate-fetch failure, create, list, delete, and trigger behavior remains unchanged.
- [x] 2.8 Run focused currency-alert service, responder, exchange-rate, and dependent integration tests.
- [x] 2.9 Stop for manual review of service state transitions and response behavior.

## 3. Cleanup and Transactional Support

- [x] 3.1 Migrate stale price-alert deletion in `CleanupService` to `price_alert_repo.delete_stale()`.
- [x] 3.2 Update cleanup and support mocks that reference `price_alert_crud` or `PriceAlertCRUD`.
- [x] 3.3 Confirm `ProfileConnectService` retains its direct `PriceAlertDB.owner_id` bulk update inside the existing cross-model transaction.
- [x] 3.4 Run focused cleanup, profile-connect, currency responder, LLM-tool, and platform integration tests.
- [x] 3.5 Stop for manual review before legacy cleanup.

## 4. Legacy Cleanup

- [x] 4.1 Search production and test code for `price_alert_crud`, `PriceAlertCRUD`, `db.schema.price_alert`, `PriceAlertSave`, and `PriceAlert.model_validate`.
- [x] 4.2 Remove legacy `price_alert_crud` access from DI after production callers are migrated.
- [x] 4.3 Remove obsolete legacy price-alert CRUD/schema tests after domain, mapper, and repository coverage is accepted.
- [x] 4.4 Remove `src/db/crud/price_alert.py`, `src/db/schema/price_alert.py`, and `SQLUtil.price_alert_crud()` after no callers remain.
- [x] 4.5 Confirm no legacy price-alert CRUD/schema references remain while intentional `PriceAlertDB` references in the DB model, Alembic, repository mapper, and profile connection remain.
- [x] 4.6 Run focused repository and all migrated consumer tests after legacy deletion.
- [x] 4.7 Stop for manual review before final verification.

## 5. Final Verification

- [x] 5.1 Run `pipenv run pytest`.
- [x] 5.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 5.3 Confirm no database migration was generated or required.
- [x] 5.4 Confirm no external API, LLM-tool, notification, or OpenAPI behavior changed.
- [x] 5.5 Validate the OpenSpec change with `openspec validate migrate-price-alert-to-repository --strict`.
- [x] 5.6 Summarize the deliberate `last_price_time` correction, retained profile-connection DB update, remaining risks, and completion status for final review.
