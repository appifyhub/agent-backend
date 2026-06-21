## Context

Price-alert persistence still uses `PriceAlertSave`, `PriceAlert`, and `PriceAlertCRUD`. `CurrencyAlertService` creates Pydantic save schemas, receives SQLAlchemy rows, converts them back to Pydantic models, and separately formats public active/triggered-alert responses. `CleanupService` calls the CRUD directly for stale deletion.

The table already has the required shape:

```
(chat_id, base_currency, desired_currency)
    composite identity, required before persistence

owner_id
    required owner reference

threshold_percent / last_price / last_price_time
    complete mutable alert state
```

`last_price_time` currently defaults through `datetime.now()` in the class declaration of the legacy Pydantic schema. That expression is evaluated when the module loads rather than for each alert instance.

The newer persistence pattern is:

```
caller
  │
  ▼
repository ─────▶ PriceAlertDB
  │                    ▲
  ▼                    │
domain dataclass ◀──── mapper
```

## Goals / Non-Goals

**Goals:**

- Introduce a price-alert domain dataclass, mapper, and repository under the currencies feature.
- Keep `PriceAlertDB` as the only SQLAlchemy model for the existing table.
- Preserve composite identity, complete-state upsert, queries, deletion, stale cleanup, and external alert behavior.
- Correct `last_price_time` so omitted timestamps default independently for each domain instance.
- Migrate production consumers and tests in reviewable milestones before removing the legacy CRUD/schema layer.

**Non-Goals:**

- No database migration or table change.
- No currency alert threshold, price calculation, notification, translation, API, LLM-tool, or OpenAPI change.
- No price-alert validation redesign or timezone migration.
- No repository conversion of the cross-model profile-connection transaction.
- No migration of chat messages, users, or the remaining persistence models touched by `ProfileConnectService`.

## Decisions

### 1. Keep One SQLAlchemy Model

`PriceAlertDB` remains the only database model and table definition. The new feature model is a dataclass mapped to and from that DB model.

**Rationale**: The existing table already expresses the required composite identity and complete alert state. A second SQLAlchemy model would duplicate metadata and introduce Alembic risk.

**Alternative considered**: Create a second SQLAlchemy representation. Rejected because it adds competing ownership without changing persistence requirements.

### 2. Use One Complete Domain Model

The domain model represents new and persisted alerts:

```
PriceAlert(
    chat_id: UUID,
    owner_id: UUID,
    base_currency: str,
    desired_currency: str,
    threshold_percent: int,
    last_price: float,
    last_price_time: datetime = field(default_factory = datetime.now),
)
```

All identity and business-state fields are required. `last_price_time` preserves the existing convenience default but evaluates it per instance. Production creation and refresh paths continue to supply the timestamp explicitly because it records when `last_price` was observed.

**Rationale**: Price alerts are internal complete-state objects. There is no generated identifier, nullable draft state, partial remote snapshot, or reason to retain a separate save model.

**Alternative considered**: Make `last_price_time` required with no default. Rejected for this migration because omitted timestamp construction is accepted today; correcting the timing bug is narrower than removing the behavior.

### 3. Preserve Composite Identity and Exact Save Semantics

The repository locates alerts by `(chat_id, base_currency, desired_currency)`.

On insert, `save` writes every domain field. On update, it preserves the composite identity used for lookup and exactly replaces `owner_id`, `threshold_percent`, `last_price`, and `last_price_time`.

```
                 ┌──────────────────────┐
                 │ PriceAlert domain    │
                 │ complete alert state │
                 └──────────┬───────────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
      no existing identity          existing identity found
             │                             │
             ▼                             ▼
       insert all fields              replace mutable state
```

**Rationale**: This matches current `save` behavior while making the domain boundary explicit. None of the alert fields represent optional patch semantics.

**Alternative considered**: Retain public `create` and `update` methods. Rejected because production creation can use `save`, and refresh updates can use `save` with a copied domain object.

### 4. Expose a Narrow Repository Surface

The repository provides:

- `get(chat_id, base_currency, desired_currency) -> PriceAlert | None`
- `get_all(skip, limit) -> list[PriceAlert]`
- `get_all_by_chat(chat_id) -> list[PriceAlert]`
- `save(price_alert) -> PriceAlert`
- `delete(chat_id, base_currency, desired_currency) -> PriceAlert | None`
- `delete_stale(cutoff) -> int`

**Rationale**: These operations cover all production behavior and equivalent legacy tests without exposing unused CRUD mechanics. `get_all_by_chat` follows current repository naming conventions.

### 5. Keep Domain State Inside CurrencyAlertService

`CurrencyAlertService` should retrieve domain alerts from the repository and map them to its existing `ActiveAlert` and `TriggeredAlert` response models only at public boundaries. Trigger refreshes should use `dataclasses.replace(existing, last_price = ..., last_price_time = ...)` before saving.

**Rationale**: This avoids converting persisted timestamps into formatted strings and then reconstructing persistence input. It also makes preservation of owner, identity, and threshold explicit.

**Alternative considered**: Reconstruct a fresh domain alert from `ActiveAlert`. Rejected because it introduces an avoidable lossy domain-to-presentation-to-domain round trip.

### 6. Leave Profile Connection's Direct Bulk Update Intact

`ProfileConnectService` directly updates `PriceAlertDB.owner_id` as one operation in a transaction that also migrates chat messages, sponsorships, and users. This change leaves that operation and its tests unchanged.

**Rationale**: It does not use `PriceAlertCRUD`, and moving only one update behind a committing repository would risk breaking cross-model atomicity. A transaction-aware persistence redesign belongs to the profile-connection feature.

**Alternative considered**: Add `reassign_owner(..., commit = False)` to the price-alert repository. Rejected because commit flags leak unit-of-work control into a repository solely for an unrelated orchestration flow.

### 7. Migrate in Reviewable Milestones

Add the repository beside the CRUD, migrate the semantic owner and cleanup caller, then remove legacy types only after reference searches are clean.

**Rationale**: Keeping both paths temporarily allows direct behavior comparison and manual review without changing the database.

## Risks / Trade-offs

- **Per-instance timestamp correction changes omitted `last_price_time` values** -> Use `field(default_factory = datetime.now)` explicitly; production paths continue supplying explicit values.
- **Composite-key lookup changes and duplicate alerts are created** -> Preserve the exact three-field identity and mirror CRUD get/upsert tests.
- **Full save accidentally loses owner or threshold state during refresh** -> Fetch domain alerts and use `dataclasses.replace` for `last_price` and `last_price_time` only.
- **Active/triggered response formatting changes** -> Keep the existing Pydantic response models and run currency service, responder, LLM-tool, and integration tests.
- **Stale cleanup deletes different rows** -> Preserve the strict `last_price_time < cutoff` predicate and verify stale/fresh counts.
- **Profile merge loses transaction atomicity** -> Leave its direct SQLAlchemy bulk update unchanged.

## Migration Plan

1. Add the domain model, mapper, repository, DI property, SQL test helper, and focused mapper/repository tests beside the legacy implementation.
2. Manually review composite identity, timestamp defaulting, and full-save behavior.
3. Migrate `CurrencyAlertService` and its tests to repository domain models and dataclass replacement.
4. Migrate `CleanupService` and related mocks to stale deletion through the repository.
5. Run responder, LLM-tool, profile-connect, and integration behavior tests.
6. Remove legacy DI access, CRUD/schema files, helpers, and obsolete tests after reference searches are clean.
7. Run the full offline suite, all-files pre-commit, and strict OpenSpec validation.

Rollback remains straightforward before legacy deletion because the database schema is unchanged and both persistence paths target the same table.

## Open Questions

None. Price-alert state is internal and complete, and the profile-connection transaction remains explicitly outside this migration boundary.
