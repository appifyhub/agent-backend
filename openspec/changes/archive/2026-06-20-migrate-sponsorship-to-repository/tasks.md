## 1. Repository Foundation

- [x] 1.1 Create the feature-level sponsorship package/domain dataclass while leaving `SponsorshipDB` as the only SQLAlchemy model.
- [x] 1.2 Create `sponsorship_mapper.py` with DB-to-domain and domain-to-DB conversion, including composite identity, `sponsored_at`, and `accepted_at` field coverage.
- [x] 1.3 Ensure mapper insert conversion writes the domain `sponsored_at` value while the DB default remains only a fallback.
- [x] 1.4 Ensure mapper/repository update conversion writes domain state exactly and acceptance updates preserve `sponsored_at` by replacing an existing domain model.
- [x] 1.5 Create `SponsorshipRepository` with `get`, `get_all_by_sponsor`, `get_all_by_receiver`, `get_all`, `save`, `delete`, `delete_all_by_receiver`, and `delete_unaccepted_older_than`.
- [x] 1.6 Wire `sponsorship_repo` into `src/di/di.py` without removing `sponsorship_crud`.
- [x] 1.7 Add `sponsorship_repo()` to `test/db/sql_util.py`.
- [x] 1.8 Add mapper tests covering DB/domain round trips, composite key identity, pending/accepted states, `sponsored_at` domain-default behavior, and `accepted_at = None` business state.
- [x] 1.9 Add repository tests mirroring existing `test/db/crud/test_sponsorship.py` behavior plus timestamp null-semantics coverage.
- [x] 1.10 Run focused sponsorship repository and legacy CRUD tests.
- [x] 1.11 Stop for manual review of the new repository shape before migrating production callers.

## 2. Sponsorship Service Migration

- [x] 2.1 Migrate `SponsorshipService.sponsor_user` to create sponsorships through `sponsorship_repo.save`.
- [x] 2.2 Migrate `SponsorshipService.accept_sponsorship` to update `accepted_at` through `sponsorship_repo.save` while preserving `sponsored_at`.
- [x] 2.3 Migrate `SponsorshipService.unsponsor_by_user_id`, `unsponsor_user`, and `unsponsor_self` to repository get/delete methods.
- [x] 2.4 Replace service-level `Sponsorship.model_validate(...)` conversions with repository domain models.
- [x] 2.5 Update sponsorship service tests and mocks for repository usage and domain model return values.
- [x] 2.6 Run focused sponsorship service tests.
- [x] 2.7 Stop for manual review of sponsorship state-transition behavior.

## 3. Sponsorship Controller Migration

- [x] 3.1 Migrate `SponsorshipsController.fetch_sponsorships` to consume repository domain models while preserving response shape and sorting/skip behavior.
- [x] 3.2 Migrate post-create sponsorship lookup in `SponsorshipsController.sponsor_user` to `sponsorship_repo.get`.
- [x] 3.3 Update sponsorship controller tests and mocks for repository usage.
- [x] 3.4 Verify sponsorship API responses, validation errors, authorization checks, and missing-receiver behavior remain unchanged.
- [x] 3.5 Run focused sponsorship controller tests.
- [x] 3.6 Stop for manual review of sponsorship API behavior.

## 4. Secondary Caller Migration

- [x] 4.1 Migrate settings-controller sponsorship checks to `sponsorship_repo`.
- [x] 4.2 Migrate credit transfer sponsored-user restrictions to `sponsorship_repo`.
- [x] 4.3 Migrate cleanup stale sponsorship deletion to `sponsorship_repo`.
- [x] 4.4 Migrate chat responder, currency alert, release summary, and other support test mocks/callers that reference `sponsorship_crud`.
- [x] 4.5 Update affected unit tests and mocks for migrated secondary callers.
- [x] 4.6 Run focused settings, transfer, cleanup, responder, and support tests.
- [x] 4.7 Stop for manual review before legacy cleanup.

## 5. Legacy Cleanup

- [x] 5.1 Search production and test code for `sponsorship_crud`, `SponsorshipCRUD`, `db.schema.sponsorship`, `SponsorshipSave`, and `Sponsorship.model_validate`.
- [x] 5.2 Remove legacy `sponsorship_crud` access from DI after production callers are migrated.
- [x] 5.3 Replace remaining test-only `sponsorship_crud` / `SponsorshipSave` fixture setup in DB CRUD tests.
- [x] 5.4 Remove obsolete legacy sponsorship CRUD tests after repository coverage is accepted as the replacement.
- [x] 5.5 Remove legacy `db/crud/sponsorship.py`, `db/schema/sponsorship.py`, and `SQLUtil.sponsorship_crud()` after no production or test references remain.
- [x] 5.6 Confirm no production or test references to legacy sponsorship CRUD/schema remain.
- [x] 5.7 Stop for manual review before final verification.

## 6. Final Verification

- [x] 6.1 Run `pipenv run pytest`.
- [x] 6.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 6.3 Confirm no database migration was generated or required for this change.
- [x] 6.4 Confirm no external API/OpenAPI behavior changed.
- [x] 6.5 Validate the OpenSpec change with `openspec validate migrate-sponsorship-to-repository --strict`.
- [x] 6.6 Summarize remaining risks and completion status for final review.
