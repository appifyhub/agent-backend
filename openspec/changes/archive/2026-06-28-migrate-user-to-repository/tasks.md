## 1. User Persistence Foundation

- [x] 1.1 Create a feature-level user package with `user.py`, `user_remote_data.py`, `user_mapper.py`, and `user_repo.py`.
- [x] 1.2 Create the complete `User` dataclass with all persisted fields, `id: UUID | None = None`, `created_at: date | None = None`, and connect-key default generation.
- [x] 1.3 Create `UserRemoteData` with only platform snapshot fields and no internal id, connect key, created-at, credits, group, secrets, tool choices, or onboarding flags.
- [x] 1.4 Confirm `UserDB` and `src/db/alembic/env.py` retain the existing `simulants` table, encrypted columns, unique constraints, indexes, defaults, enum, and require no migration.
- [x] 1.5 Create `user_mapper.domain()` and `user_mapper.db()` with full field coverage and `SecretStr` wrapping/unwrapping.
- [x] 1.6 Create `user_mapper.apply_to_db_model()` that mutates mutable persisted fields, clears nullable fields when the domain value is `None`, and preserves `id` and `created_at`.
- [x] 1.7 Create `user_mapper.from_remote_data(remote_data)`.
- [x] 1.8 Create `user_mapper.apply_remote_data(existing_user, remote_data)` with explicit platform-field ownership and full-name fill-only behavior.
- [x] 1.9 Create `UserRepository` with `get`, `get_all`, `count`, platform lookup methods, `get_by_connect_key`, `get_by_remote_data`, `save`, and `delete`.
- [x] 1.10 Add `update_locked` and `update_locked_pair` repository methods using `with_for_update()` and domain callback return values.
- [x] 1.11 Wire `user_repo` into `src/di/di.py` beside `user_crud`.
- [x] 1.12 Add `user_repo()` to `test/db/sql_util.py` while retaining the legacy CRUD helper.
- [x] 1.13 Add mapper tests for DB/domain conversion, all encrypted fields, nullable clearing, connect-key handling, remote creation, remote merge, and identity/created-at preservation.
- [x] 1.14 Add repository tests mirroring legacy user CRUD behavior: get, get_all, count, platform lookups, connect-key lookup, insert, update, delete, missing rows, and secret persistence.
- [x] 1.15 Add repository tests for `get_by_remote_data`, locked single-user updates, locked pair updates, deterministic lock ordering, and missing-user errors.
- [x] 1.16 Run focused user mapper, repository, legacy CRUD, and dependent persistence tests.
- [x] 1.17 Stop for manual review of domain shape, remote-data shape, field ownership, secret conversion, generated fields, repository surface, and lock semantics.

## 2. Platform User Resolution

- [x] 2.1 Migrate `TelegramDomainMapper.Result` and `map_author` from `UserSave` to `UserRemoteData`.
- [x] 2.2 Preserve Telegram full name, username, private chat id, and user id mapping in remote data.
- [x] 2.3 Migrate `TelegramDataResolver.Result` and `resolve_author` to use `user_repo`, `get_by_remote_data`, `from_remote_data`, `apply_remote_data`, and complete `User` domain objects.
- [x] 2.4 Keep Telegram capacity checks and onboarding defaults outside the repository before converting new remote users to complete domain state.
- [x] 2.5 Verify Telegram existing-user resolution preserves user-owned fields and applies only non-null Telegram-owned fields.
- [x] 2.6 Migrate `WhatsAppDomainMapper.Result` and `map_author` from `UserSave` to `UserRemoteData`.
- [x] 2.7 Preserve WhatsApp full name, user id, and phone-number mapping in remote data.
- [x] 2.8 Migrate `WhatsAppDataResolver.Result` and `resolve_author` to use `user_repo`, `get_by_remote_data`, `from_remote_data`, `apply_remote_data`, and complete `User` domain objects.
- [x] 2.9 Keep WhatsApp capacity checks and onboarding defaults outside the repository before converting new remote users to complete domain state.
- [x] 2.10 Verify WhatsApp existing-user resolution preserves user-owned fields and applies only non-null WhatsApp-owned fields.
- [x] 2.11 Update Telegram and WhatsApp mapper/resolver tests for remote data, existing-user preservation, new-user defaults, capacity handling, membership sync, messages, and attachments.
- [x] 2.12 Run focused Telegram and WhatsApp mapper, resolver, update-responder, chat-agent, membership, and attachment tests.
- [x] 2.13 Stop for manual review of platform user mapping, remote merge behavior, and onboarding default placement.

## 3. Authorization and Settings

- [x] 3.1 Migrate `AuthorizationService.validate_user` to use `user_repo` while preserving malformed-ID and user-not-found errors.
- [x] 3.2 Migrate `AuthorizationService.require_waitlisted_user_can_activate` to use `user_repo.count()`.
- [x] 3.3 Update DI `invoker` typing and injection paths to use the new user domain model.
- [x] 3.4 Migrate `api.mapper.user_mapper` from legacy schema types to the feature-level `User` domain and dataclass replacement.
- [x] 3.5 Migrate `SettingsController.save_user_settings` to save complete user domain state through `user_repo`.
- [x] 3.6 Verify user settings response shape, masked secrets, policy-acceptance validation, waitlist activation, and tool-choice validation remain unchanged.
- [x] 3.7 Update authorization, settings-controller, user-mapper, and API tests/mocks for user domain and repository usage.
- [x] 3.8 Run focused authorization, settings, external-tools, products, JWT/settings-link, and user-mapper tests.
- [x] 3.9 Stop for manual review of authorization, DI invoker, and settings user writes.

## 4. User Lookup Consumers

- [x] 4.1 Migrate integration helper functions from `User | UserSave` unions to the feature-level user domain and remote/create helper types where needed.
- [x] 4.2 Migrate `resolve_agent_user`, `THE_AGENT`, and `BACKGROUND_AGENT` to construct feature-level user domain objects or explicit agent user fixtures.
- [x] 4.3 Migrate `lookup_user_by_handle` to use `UserRepository` and return domain users.
- [x] 4.4 Migrate `resolve_user_to_save` callers to construct complete domain users through mapper/helper functions rather than legacy `UserSave`.
- [x] 4.5 Migrate `SponsorshipService` and `SponsorshipsController` user lookups, receiver creation, capacity checks, and response mapping to `user_repo`.
- [x] 4.6 Migrate `AccessTokenResolver`, `UsageTrackingService`, `ChatAgent`, `ChatMembershipService`, `PlatformBotSDK`, prompt resolvers, dev announcements, support paths, and remaining read/write consumers to user domain objects.
- [x] 4.7 Update tests and mocks for integration helpers, sponsorships, access-token resolution, usage tracking, chat membership, chat agent, prompt resolvers, announcements, and support.
- [x] 4.8 Run focused sponsorship, integration, external-tools, usage, chat membership, chat-agent, prompt, announcement, and support tests.
- [x] 4.9 Stop for manual review of broad user lookup consumers before accounting lock migration.

## 5. Accounting Locked Updates

- [x] 5.1 Migrate `SpendingService.validate_pre_flight` user lookup to `user_repo`.
- [x] 5.2 Migrate `SpendingService.deduct` to `user_repo.update_locked()` with a domain callback that returns updated user state.
- [x] 5.3 Migrate purchase credit allocation and deallocation to `user_repo.update_locked()` while preserving balance math and logging.
- [x] 5.4 Migrate `CreditTransferService` sender and receiver lookup to `user_repo` and repository-backed handle lookup.
- [x] 5.5 Migrate `CreditTransferService` transfer mutation to `user_repo.update_locked_pair()` with deterministic lock ordering and domain callback return values.
- [x] 5.6 Verify insufficient-credit, sponsored-user restriction, self-transfer, missing-recipient, purchase allocation, refund deallocation, and usage-record behavior remain unchanged.
- [x] 5.7 Update accounting spending, purchases, transfers, usage, and controller tests/mocks for repository usage and domain callbacks.
- [x] 5.8 Run focused spending, purchase, transfer, usage, sponsorship restriction, and controller tests.
- [x] 5.9 Stop for manual review of locked credit updates and accounting behavior.

## 6. Profile Connection

- [x] 6.1 Migrate profile-connect validation and target lookup to feature-level `User` and `user_repo`.
- [x] 6.2 Migrate profile merge data construction from `UserSave` to dataclass replacement or a mapper/helper that returns complete `User` domain state.
- [x] 6.3 Preserve dependent-entity direct bulk updates for chat messages, price alerts, and sponsorships inside the existing profile-connect transaction.
- [x] 6.4 Replace legacy user CRUD delete/update calls inside the profile-connect transaction with a transaction-safe approach that preserves atomicity and avoids ordinary committing repository methods.
- [x] 6.5 Regenerate survivor connect keys without legacy schema types and preserve rollback behavior on failure.
- [x] 6.6 Verify compatible profile merge, incompatible profile rejection, survivor/casualty selection, dependent-record migration, connect-key regeneration, and rollback behavior.
- [x] 6.7 Update profile-connect service/controller tests and affected repository fixtures.
- [x] 6.8 Run focused profile-connect, chat-message, price-alert, sponsorship, user repository, and transaction behavior tests.
- [x] 6.9 Stop for manual review of profile connection and transaction handling.

## 7. Legacy User Cleanup

- [x] 7.1 Search production and test code for `user_crud`, `UserCRUD`, `db.schema.user`, `UserSave`, and `User.model_validate`.
- [x] 7.2 Remove legacy `user_crud` type, cache, and property from DI after all production callers migrate.
- [x] 7.3 Migrate remaining test fixtures from `UserSave` and `user_crud()` to user domain and `user_repo()`.
- [x] 7.4 Remove obsolete legacy user CRUD tests after mapper, repository, and consumer coverage is accepted.
- [x] 7.5 Remove `src/db/crud/user.py`, `src/db/schema/user.py`, and `SQLUtil.user_crud()` after no callers remain.
- [x] 7.6 Confirm intentional `UserDB` references remain only in SQLAlchemy model ownership, Alembic registration, enum usage, mapper/repository persistence, and documented transaction seams.
- [x] 7.7 Run focused user repository, platform resolver, settings, authorization, sponsorship, accounting, profile-connect, chat, integration, and support tests after legacy deletion.
- [ ] 7.8 Stop for manual review before final verification.

## 8. Final Verification

- [ ] 8.1 Run `pipenv run pytest`.
- [ ] 8.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [ ] 8.3 Confirm no Alembic migration was generated or required and the database schema is unchanged.
- [ ] 8.4 Confirm no route, payload, response, JWT, settings, sponsorship, purchase, transfer, prompt, notification, or OpenAPI behavior changed.
- [ ] 8.5 Confirm user remote snapshots, DB-owned field preservation, secret conversion, connect-key generation, waitlist defaults, locked updates, and profile connection remain compatible.
- [ ] 8.6 Validate the OpenSpec change with `openspec validate migrate-user-to-repository --strict`.
- [ ] 8.7 Summarize the remote/complete state split, repository surface, lock semantics, profile-connect transaction decision, remaining risks, and completion status for final review.
