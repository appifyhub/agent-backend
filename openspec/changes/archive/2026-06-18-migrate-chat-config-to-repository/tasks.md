## 1. Repository Foundation

- [x] 1.1 Create the feature-level chat config package and domain dataclass while leaving `ChatConfigDB` as the only SQLAlchemy model.
- [x] 1.2 Create `chat_config_mapper.py` with DB-to-domain and domain-to-DB conversion, including full field coverage and `None` handling.
- [x] 1.3 Create `ChatConfigRepository` with `get`, `get_all`, `get_by_external_identifiers`, `save(ChatConfig | ChatConfigRemoteData)`, and `delete`.
- [x] 1.4 Add `ChatConfigRemoteData` and mapper-owned remote conversion/merge behavior for snapshot saves.
- [x] 1.5 Wire `chat_config_repo` into `src/di/di.py` without removing or changing `chat_config_crud`.
- [x] 1.6 Add `chat_config_repo()` to `test/db/sql_util.py`.
- [x] 1.7 Add mapper tests covering DB/domain round trips, enum fields, remote snapshot conversion, remote merge behavior, and `None` handling.
- [x] 1.8 Add repository tests mirroring existing `test/db/crud/test_chat_config.py` behavior plus `ChatConfigRemoteData` save behavior.
- [x] 1.9 Run focused repository and legacy CRUD tests.
- [x] 1.10 Stop for manual review of the new repository shape before migrating production callers.

## 2. Settings Controller Migration

- [x] 2.1 Replace direct chat config CRUD reads in `SettingsController.fetch_all_chat_settings` with `chat_config_repo`.
- [x] 2.2 Replace direct chat config CRUD writes in `SettingsController.__apply_chat_config_changes` with `chat_config_repo`.
- [x] 2.3 Update settings-controller mocks and fixtures to use the new chat config domain model for migrated paths.
- [x] 2.4 Verify settings API responses, validation errors, authorization checks, and chat sorting remain unchanged.
- [x] 2.5 Run focused settings tests.
- [x] 2.6 Stop for manual review of the settings-controller migration.

## 3. Platform Resolver Migration

- [x] 3.1 Migrate Telegram chat config resolution to build `ChatConfigRemoteData` and call `chat_config_repo.save(remote_data)`.
- [x] 3.2 Replace Telegram resolver mutation of incoming mapped data with explicit remote snapshot persistence.
- [x] 3.3 Preserve existing Telegram behavior for DB-owned fields: language, reply chance, release notifications, and media mode; update non-null remote-owned `is_private`.
- [x] 3.4 Migrate WhatsApp chat config resolution with the same remote snapshot repository pattern.
- [x] 3.5 Preserve existing WhatsApp behavior for DB-owned fields: language, reply chance, release notifications, and media mode; update non-null remote-owned `is_private`.
- [x] 3.6 Update Telegram and WhatsApp resolver tests to assert existing-chat preservation, new-chat defaults, and no mutation dependency on legacy `ChatConfigSave` persistence behavior.
- [x] 3.7 Run focused Telegram and WhatsApp resolver tests.
- [x] 3.8 Stop for manual review of platform resolver behavior.

## 4. Remaining Production Caller Migration

- [x] 4.1 Migrate lower-risk chat config lookup paths in integrations, announcements, SDKs, responders, and support code from legacy CRUD/schema use to the repository/domain model.
- [x] 4.2 Update affected unit tests and mocks for migrated lower-risk callers.
- [x] 4.3 Run focused tests for migrated integration, announcement, SDK, and responder paths.
- [x] 4.4 Stop for manual review before migrating authorization.

## 5. Authorization Migration

- [x] 5.1 Migrate `AuthorizationService.validate_chat` to use `chat_config_repo` while preserving malformed-ID and not-found error behavior.
- [x] 5.2 Migrate `AuthorizationService.get_authorized_chats` to consume repository domain models while preserving admin-discovery behavior and sort order.
- [x] 5.3 Update DI `invoker_chat` typing and related tests for the new chat config domain model.
- [x] 5.4 Update authorization tests for migrated repository usage.
- [x] 5.5 Run focused authorization and settings tests.
- [x] 5.6 Stop for manual review of authorization behavior.

## 6. Legacy Cleanup

- [x] 6.1 Search production code for `chat_config_crud`, `db.schema.chat_config`, `ChatConfig.model_validate`, and `ChatConfigSave`.
- [x] 6.2 Remove legacy `chat_config_crud` access from DI after production callers are migrated.
- [x] 6.3 Confirm production references to legacy chat config CRUD/schema remain only in the legacy CRUD/schema modules themselves.
- [x] 6.4 Replace remaining test-only `chat_config_crud` / `ChatConfigSave` fixture setup in DB CRUD tests for chat messages, chat message attachments, and price alerts.
- [x] 6.5 Remove obsolete legacy chat config CRUD tests after repository coverage is accepted as the replacement.
- [x] 6.6 Remove legacy `db/crud/chat_config.py`, `db/schema/chat_config.py`, and `SQLUtil.chat_config_crud()` after no production or test references remain.
- [x] 6.7 Update migrated API/feature test fixtures to use the new domain model and repository helpers.
- [x] 6.8 Run the broad chat/settings/authorization/platform test set.
- [x] 6.9 Stop for manual review before final verification.

## 7. Final Verification

- [x] 7.1 Run `pipenv run pytest`.
- [x] 7.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 7.3 Confirm no database migration was generated or required for this change.
- [x] 7.4 Confirm no external API/OpenAPI behavior changed.
- [x] 7.5 Summarize remaining risks and completion status for final review.
