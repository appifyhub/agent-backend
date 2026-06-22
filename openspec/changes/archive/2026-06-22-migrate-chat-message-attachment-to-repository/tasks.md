## 1. Attachment Persistence Foundation

- [x] 1.1 Create `src/features/chat/attachment/chat_message_attachment.py` with a complete `ChatMessageAttachment` dataclass, required `chat_id`, optional unsaved `id`, nullable metadata, and unchanged `has_stale_data` behavior.
- [x] 1.2 Create `chat_message_attachment_remote_data.py` with pre-resolution platform fields and no internal attachment/chat IDs.
- [x] 1.3 Add `default = generate_short_uuid` to `ChatMessageAttachmentDB.id` while retaining the existing table, primary key, foreign key, index, and nullability.
- [x] 1.4 Confirm `src/db/alembic/env.py` still imports the single `ChatMessageAttachmentDB` model and that the Python-side ID default requires no migration.
- [x] 1.5 Create `chat_message_attachment_mapper.py` with complete DB-to-domain and domain-to-DB conversion.
- [x] 1.6 Use the existing deterministic short-UUID utility in `from_remote_data(remote_data, chat_id)` conversion that produces complete domain state.
- [x] 1.7 Add `apply_remote_data(existing, remote_data)` that preserves existing ID/chat ID and exactly matches current truthy metadata fallback behavior.
- [x] 1.8 Create `ChatMessageAttachmentRepository` with `get`, `get_by_external_id`, `get_all`, `get_all_by_message`, `save`, `delete`, and `delete_by_old_messages`.
- [x] 1.9 Ensure repository save inserts complete state, generates omitted IDs through SQLAlchemy, and exactly replaces every non-ID field on update.
- [x] 1.10 Preserve first-match external-ID lookup and the exact old-message subquery, strict cutoff, cleanup count, and commit behavior.
- [x] 1.11 Wire `chat_message_attachment_repo` into `src/di/di.py` beside `chat_message_attachment_crud`.
- [x] 1.12 Add `chat_message_attachment_repo()` to `test/db/sql_util.py` while retaining the CRUD helper.
- [x] 1.13 Add focused domain tests only for stale URL behavior, not standard dataclass construction.
- [x] 1.14 Add mapper tests for DB/domain round trips, deterministic remote ID derivation, remote creation, identity preservation, truthy overrides, and falsey fallback.
- [x] 1.15 Add repository tests for ID/external/message queries, pagination, generated and deterministic IDs, insert, exact update, deletion, and old-message cleanup.
- [x] 1.16 Run focused domain, mapper, repository, legacy CRUD/schema, chat-message, and cleanup persistence tests.
- [x] 1.17 Stop for manual review of attachment states, ID generation, merge rules, repository surface, and database impact.

## 2. Low-Risk Domain Consumers

- [x] 2.1 Migrate `UrlAttachmentResolver` to construct the complete attachment domain model with its explicit virtual ID/chat/message state.
- [x] 2.2 Migrate `ChatAttachmentProcessor` and `ChatImageEditService` attachment type imports to the domain model without changing media behavior.
- [x] 2.3 Migrate `ChatAgent` message-scoped attachment lookup from CRUD rows/Pydantic conversion to repository domain results.
- [x] 2.4 Update affected URL resolver, attachment processor, image edit, and chat-agent tests/mocks to use domain attachments and repository results.
- [x] 2.5 Run focused low-risk consumer tests and confirm LLM attachment IDs, media fields, and processing outputs are unchanged.
- [x] 2.6 Stop for manual review of domain-only consumers before platform pipeline migration.

## 3. Telegram Attachment Pipeline

- [x] 3.1 Migrate `TelegramDomainMapper.Result` and attachment mapping methods from `ChatMessageAttachmentSave` to `ChatMessageAttachmentRemoteData`.
- [x] 3.2 Preserve Telegram deterministic IDs through the existing deterministic short-UUID utility and use the same ID for message text, conversion, and persistence.
- [x] 3.3 Migrate `TelegramDataResolver` to fetch existing attachments through the repository and use mapper creation/merge functions after chat resolution.
- [x] 3.4 Ensure only complete domain attachments with required chat IDs are passed from the resolver into Telegram refresh.
- [x] 3.5 Simplify `TelegramBotSDK.refresh_attachment` to one complete domain input and migrate ID/batch lookup to the repository.
- [x] 3.6 Replace Telegram attachment mutation with `dataclasses.replace` while preserving fresh-save, API refresh, URL expiration, extension/MIME inference, byte detection, and structured errors.
- [x] 3.7 Persist and return Telegram attachment domain snapshots through the repository without DB/Pydantic round trips.
- [x] 3.8 Update Telegram mapper, resolver, SDK, and SDK utility tests for remote/domain inputs and repository mocks.
- [x] 3.9 Verify fresh, stale, missing external ID, missing attachment, API metadata, format detection, and batch refresh behavior.
- [x] 3.10 Run focused Telegram mapper/resolver/SDK tests plus attachment processor and platform integration canaries.
- [x] 3.11 Stop for manual review of the Telegram attachment state and refresh flow.

## 4. WhatsApp Attachment Pipeline

- [x] 4.1 Migrate `WhatsAppDomainMapper.Result` and attachment mapping methods from `ChatMessageAttachmentSave` to `ChatMessageAttachmentRemoteData`.
- [x] 4.2 Preserve WhatsApp deterministic IDs through the existing deterministic short-UUID utility and use the same ID for message text, conversion, and persistence.
- [x] 4.3 Migrate `WhatsAppDataResolver` to repository lookup and mapper creation/merge after chat resolution.
- [x] 4.4 Ensure only complete domain attachments with required chat IDs are passed from the resolver into WhatsApp refresh.
- [x] 4.5 Simplify `WhatsAppBotSDK.refresh_attachment` to one complete domain input and migrate ID/batch lookup to the repository.
- [x] 4.6 Migrate sent-media storage and re-upload helpers to complete domain objects, `dataclasses.replace`, and repository save results.
- [x] 4.7 Preserve initial WhatsApp URL persistence, download behavior, metadata refresh, permanent upload URL/expiration, MIME/extension detection, fallback behavior, and structured errors.
- [x] 4.8 Update WhatsApp mapper, resolver, SDK, sent-media, and refresh tests for remote/domain inputs and repository mocks.
- [x] 4.9 Verify fresh, stale, missing external ID, missing media info/content, upload success/failure, format detection, sent media, and batch refresh behavior.
- [x] 4.10 Run focused WhatsApp mapper/resolver/SDK tests plus attachment processor and platform integration canaries.
- [x] 4.11 Stop for manual review of the WhatsApp attachment state, upload, and refresh flow.

## 5. Shared Refresh and Cleanup Consumers

- [x] 5.1 Migrate `PlatformBotSDK` attachment refresh type boundaries to complete domain attachments after both platform SDKs are migrated.
- [x] 5.2 Migrate `chat_attachment_utils` local lookup from CRUD rows/Pydantic conversion to repository domain objects.
- [x] 5.3 Update attachment utility, processor, image-edit, Telegram/WhatsApp SDK, and platform integration support mocks that still reference attachment CRUD/schema types.
- [x] 5.4 Migrate `CleanupService` old-message attachment deletion to `chat_message_attachment_repo.delete_by_old_messages()` without changing phase ordering.
- [x] 5.5 Update cleanup tests and support mocks to assert repository deletion counts and attachment-before-message ordering.
- [x] 5.6 Run focused attachment utility, processor, image edit, chat agent, cleanup, Telegram, WhatsApp, LLM-tool, and platform integration tests.
- [x] 5.7 Stop for manual review before legacy attachment persistence deletion.

## 6. Legacy Attachment Cleanup

- [x] 6.1 Search production and test code for `chat_message_attachment_crud`, `ChatMessageAttachmentCRUD`, `db.schema.chat_message_attachment`, `ChatMessageAttachmentSave`, and `ChatMessageAttachment.model_validate`.
- [x] 6.2 Remove legacy `chat_message_attachment_crud` type, cache, and property from DI after all production callers migrate.
- [x] 6.3 Remove obsolete legacy attachment CRUD/schema tests after domain, mapper, repository, and consumer coverage is accepted.
- [x] 6.4 Remove `src/db/crud/chat_message_attachment.py`, `src/db/schema/chat_message_attachment.py`, and `SQLUtil.chat_message_attachment_crud()` after no callers remain.
- [x] 6.5 Confirm no legacy attachment CRUD/schema references remain while intentional `ChatMessageAttachmentDB` references remain only in the model, Alembic, mapper, and repository tests.
- [x] 6.6 Run focused repository and all migrated attachment consumer tests after legacy deletion.
- [x] 6.7 Stop for manual review before final verification.

## 7. Final Verification

- [x] 7.1 Run `pipenv run pytest`.
- [x] 7.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 7.3 Confirm no Alembic migration was generated or required and the database schema is unchanged.
- [x] 7.4 Confirm no attachment ID, platform API, URL refresh, upload, media detection, LLM-tool, notification, route, or OpenAPI behavior changed.
- [x] 7.5 Validate the OpenSpec change with `openspec validate migrate-chat-message-attachment-to-repository --strict`.
- [x] 7.6 Summarize the remote/complete state split, ChatConfig-style generated ID lifecycle, preserved merge semantics, remaining risks, and completion status for final review.
