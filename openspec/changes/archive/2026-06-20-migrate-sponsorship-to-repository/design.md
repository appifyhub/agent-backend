## Context

`sponsorships` still uses the legacy `db/schema` + `db/crud` persistence pattern. `SponsorshipCRUD` accepts `SponsorshipSave`, returns `SponsorshipDB`, and callers convert rows with `Sponsorship.model_validate(...)`. This leaks persistence-specific Pydantic and SQLAlchemy shapes into `SponsorshipService`, `SponsorshipsController`, transfer validation, cleanup, settings checks, and tests.

The repository pattern now exists in nearby persistence areas:

```
caller
  │
  ▼
repository ─────▶ SQLAlchemy DB model
  │                    ▲
  ▼                    │
domain dataclass ◀──── mapper
```

`UsageRecordRepository`, `PurchaseRecordRepository`, `ChatMembershipRepository`, and the newer chat config repository keep SQLAlchemy models at the persistence edge and return feature-level domain dataclasses to callers.

Sponsorship differs from chat config in one important way: it does not receive partial external platform snapshots. Sponsorship rows are internal state created, accepted, and deleted by application services. `accepted_at` is the only nullable domain state:

```
sponsor_id / receiver_id
    required composite identity, never generated

sponsored_at
    persisted timestamp, defaulted by the application domain model
    existing DB default remains only as a database fallback

accepted_at
    nullable business state
    None means "pending sponsorship"
    non-null means "accepted sponsorship"
```

## Goals / Non-Goals

**Goals:**

- Introduce a sponsorship domain dataclass, mapper, and repository that match the repository pattern used by newer persistence units.
- Keep `SponsorshipDB` as the only SQLAlchemy model for the existing `sponsorships` table.
- Preserve all current external API behavior, internal sponsorship business rules, and database schema behavior.
- Make `sponsored_at` defaulting and `accepted_at` null semantics explicit in mapper/repository tests.
- Add repository tests beside legacy CRUD tests, then migrate production callers through the new repository/domain boundary.
- Remove legacy `db/crud/sponsorship.py` and `db/schema/sponsorship.py` only after production and test references are gone.

**Non-Goals:**

- No database migration or schema change.
- No endpoint, payload, response, or OpenAPI contract change.
- No change to sponsorship eligibility rules, transitive sponsorship restrictions, waitlist behavior, transfer restrictions, or cleanup retention policy.
- No user repository migration in this change, even though sponsorship flows still depend on legacy `user_crud`.

## Decisions

### 1. Keep One SQLAlchemy Model

`SponsorshipDB` remains the only DB model and table definition for `sponsorships`.

The new model introduced by this change is a feature-level domain dataclass, not a second SQLAlchemy model or table. The repository maps between the dataclass and `SponsorshipDB`.

**Rationale**: This matches the existing repository pattern and avoids competing table definitions. The database schema already represents the desired persistence shape.

**Alternative considered**: Create a parallel SQLAlchemy model. Rejected because it duplicates table ownership and increases Alembic risk without improving the domain boundary.

### 2. Use One Domain Model for New and Persisted Sponsorships

The sponsorship domain dataclass should have required composite identity fields, a non-null sponsorship timestamp default, and nullable acceptance state:

```
Sponsorship(
    sponsor_id: UUID,
    receiver_id: UUID,
    sponsored_at: datetime = field(default_factory=datetime.now),
    accepted_at: datetime | None = None,
)
```

`sponsor_id` and `receiver_id` are always required before saving. `sponsored_at` is created by the domain model and is written to the database explicitly. `accepted_at` is intentionally nullable business state.

**Rationale**: A separate `SponsorshipSave` equivalent is unnecessary. Unlike chat config, sponsorship data is internal and does not arrive as a partial remote snapshot. Letting the domain model default `sponsored_at` keeps the app and DB representations aligned without carrying a fake nullable state.

**Alternative considered**: Keep separate create/save and persisted domain models. Rejected because it retains the old split without adding meaningful safety.

### 3. Write Domain State Exactly

Repository save behavior should be explicit:

- Insert:
  - require `sponsor_id` and `receiver_id`;
  - write the domain `sponsored_at` value;
  - include `accepted_at` exactly as provided, including `None`.
- Update:
  - locate the row by `(sponsor_id, receiver_id)`;
  - write the domain `sponsored_at` value;
  - write `accepted_at` exactly as provided, including `None`.

```
                 ┌──────────────────────┐
                 │ Sponsorship domain    │
                 │ sponsor_id required   │
                 │ receiver_id required  │
                 │ sponsored_at default  │
                 │ accepted_at optional  │
                 └──────────┬───────────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
      no existing row                existing row found
             │                             │
             ▼                             ▼
 write sponsored_at                 write sponsored_at
 write accepted_at                  write accepted_at
 even when None                     even when None
```

**Rationale**: `accepted_at = None` means pending and must not be treated like an absent update value. `sponsored_at` is ordinary domain state; callers that update acceptance should preserve it by copying/replacing the existing domain model.

**Alternative considered**: Keep `sponsored_at` nullable and let the DB generate it. Rejected because this creates ambiguity in the domain model.

### 4. Keep Query Methods Aligned with Current CRUD Names First

The first repository should preserve the current operation surface:

- `get(sponsor_id, receiver_id) -> Sponsorship | None`
- `get_all_by_sponsor(sponsor_id, skip, limit) -> list[Sponsorship]`
- `get_all_by_receiver(receiver_id, skip, limit) -> list[Sponsorship]`
- `get_all(skip, limit) -> list[Sponsorship]`
- `save(sponsorship) -> Sponsorship`
- `delete(sponsor_id, receiver_id) -> Sponsorship | None`
- `delete_all_by_receiver(receiver_id) -> int`
- `delete_unaccepted_older_than(cutoff) -> int`

**Rationale**: Matching method names keeps production migration focused on type boundaries rather than business flow redesign.

**Alternative considered**: Rename methods around domain language, such as `find_received_by_user` or `delete_pending_before`. Rejected for the first pass because it expands review scope.

### 5. Migrate Callers Through Service Boundaries

The new repository should be added to DI first, while legacy CRUD remains available. Then production callers can migrate in bounded steps:

1. Repository/domain/mapper/DI and tests only.
2. `SponsorshipService`, where creation, acceptance, and deletion state transitions are centralized.
3. `SponsorshipsController`, preserving response shape and post-create lookup behavior.
4. Secondary read/delete callers: settings checks, transfer validation, cleanup service, responder/support paths.
5. Remove legacy DI access after production callers are gone.
6. Remove legacy CRUD/schema/tests after remaining test fixtures and mocks are migrated.

**Rationale**: Sponsorship service is the semantic owner of sponsorship state. Migrating it early lets the rest of the application consume the new domain shape without changing business rules.

**Alternative considered**: Big-bang replace every `sponsorship_crud` and `db.schema.sponsorship` import. Rejected because controller/service tests are numerous and the boundary is easier to review in milestones.

## Risks / Trade-offs

- **`accepted_at=None` is mistaken for "do not update"** -> Mitigation: mapper and repository tests must explicitly cover clearing/pending behavior and accepting behavior.
- **Fresh update objects can accidentally change `sponsored_at`** -> Mitigation: service migration should fetch the existing sponsorship and use dataclass replacement for acceptance changes.
- **Mixed DB/domain sponsorship types during migration** -> Mitigation: migrate one owner boundary at a time and keep focused tests green after each milestone.
- **Controller response shape changes accidentally** -> Mitigation: use sponsorship controller tests as API behavior canaries.
- **Cleanup or transfer restrictions regress** -> Mitigation: run focused cleanup and credit transfer tests after those callers migrate.

## Migration Plan

1. Add the sponsorship domain model, mapper, repository, DI property, and SQL test helper.
2. Add mapper and repository tests that mirror the existing CRUD behavior and specifically cover timestamp null semantics.
3. Migrate `SponsorshipService` to the repository and domain model.
4. Migrate `SponsorshipsController` and preserve exact response behavior.
5. Migrate secondary callers in settings, transfers, cleanup, and chat responder/support paths.
6. Remove legacy DI access to `sponsorship_crud` once production callers use the repository.
7. Replace remaining test fixtures/mocks that import `SponsorshipCRUD` or `db.schema.sponsorship`.
8. Remove legacy sponsorship CRUD/schema files and obsolete CRUD tests.
9. Run the full offline test suite and pre-commit before closing implementation.

Rollback during the transition is straightforward because the database schema does not change and legacy CRUD remains available until the final removal milestone.

## Open Questions

None. Sponsorship state is internal-only, and `accepted_at` remains an intentional nullable domain field.
