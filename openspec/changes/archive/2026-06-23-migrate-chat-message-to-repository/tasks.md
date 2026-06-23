## 1. Message Persistence Foundation

- [x] 1.1 Create `src/features/chat/message/chat_message.py` with a complete `ChatMessage` dataclass, required composite identity, optional author, encrypted-text value, and construction-time `sent_at` default factory.
- [x] 1.2 Create `chat_message_remote_data.py` with required platform message ID, timestamp, and text and no internal chat or author IDs.
- [x] 1.3 Confirm `ChatMessageDB` and `src/db/alembic/env.py` retain the existing table, composite primary key, foreign keys, unique constraint, encryption, timestamp default, and require no migration.
- [x] 1.4 Create `chat_message_mapper.py` with explicit DB-to-domain and domain-to-DB conversion.
- [x] 1.5 Add `from_remote_data(remote_data, chat_id, author_id)` conversion that produces complete domain state.
- [x] 1.6 Add `apply_remote_data(existing, remote_data, author_id)` that preserves composite identity, falls back to the existing author only when the resolved author is absent, and applies incoming timestamp and text.
- [x] 1.7 Create `ChatMessageRepository` with `get`, `get_all`, `get_latest_by_chat`, `save`, `delete`, and `delete_older_than`.
- [x] 1.8 Ensure repository save inserts complete state and exactly replaces author, timestamp, and text on composite-key updates.
- [x] 1.9 Preserve latest-message descending order, chat filtering, pagination, strict cleanup cutoff, deleted-row count, and commit behavior.
- [x] 1.10 Wire `chat_message_repo` into `src/di/di.py` beside `chat_message_crud`.
- [x] 1.11 Add `chat_message_repo()` to `test/db/sql_util.py` while retaining the CRUD helper.
- [x] 1.12 Add focused domain tests for construction-time timestamp generation only, not standard dataclass behavior.
- [x] 1.13 Add mapper tests for DB/domain round trips, remote creation, stable composite identity, author replacement/fallback, and edited timestamp/text application.
- [x] 1.14 Add repository tests for composite lookup, missing lookup, pagination, latest ordering, insert, exact update from independent snapshots, deletion, and retention cleanup.
- [x] 1.15 Run focused domain, mapper, repository, legacy CRUD/schema, chat attachment repository, and cleanup persistence tests.
- [x] 1.16 Move existing-row application from private repository copy helpers into `apply_to_db_model` mapper functions for messages, attachments, chat configs, tools cache, sponsorships, and price alerts.
- [x] 1.17 Extend all six mapper test suites to verify mutable field application, nullable clearing, and identity preservation.
- [x] 1.18 Stop for manual review of message states, timestamp correction, merge rules, mapper/repository ownership, repository surface, composite identity, and database impact.

## 2. Read-Only Message Consumers

- [x] 2.1 Migrate `ChatAgent` history loading from CRUD rows/Pydantic conversion to `chat_message_repo.get_latest_by_chat()` domain results.
- [x] 2.2 Migrate `ChatAgent` burst detection and unanswered-mention history queries to repository domain results without changing ordering or filtering.
- [x] 2.3 Migrate integration private-chat activity lookup to repository domain results without changing platform eligibility windows.
- [x] 2.4 Migrate `DomainLangchainMapper.map_to_langchain` and other read-only message type boundaries to the complete domain model.
- [x] 2.5 Update chat-agent, domain-LangChain mapper, and integration tests/mocks to use repository results and domain messages.
- [x] 2.6 Run focused chat-agent, mapper, integration, attachment-history, debounce, mention, and private-chat eligibility tests.
- [x] 2.7 Stop for manual review of read-only history consumers before platform ingress migration.

## 3. Telegram Message Ingress

- [x] 3.1 Migrate `TelegramDomainMapper.Result` and `map_message` from `ChatMessageSave` to `ChatMessageRemoteData`.
- [x] 3.2 Preserve Telegram message ID, edit timestamp selection, reply/quote text, caption, body, and attachment-text formatting in remote data.
- [x] 3.3 Migrate `TelegramDataResolver.Result` to the complete message domain model.
- [x] 3.4 Replace Telegram resolver mutation with explicit remote creation or merge after chat and author resolution.
- [x] 3.5 Migrate Telegram existing-message lookup and persistence to `ChatMessageRepository`.
- [x] 3.6 Verify Telegram edits preserve composite identity, preserve an existing author only when no new author resolves, and replace timestamp/text.
- [x] 3.7 Update Telegram mapper and resolver tests for remote/domain inputs, repository results, new messages, edits, missing authors, and attachments.
- [x] 3.8 Run focused Telegram mapper, resolver, SDK-send, update-responder, chat-agent, and attachment pipeline canaries.
- [x] 3.9 Stop for manual review of Telegram message mapping, merge, and persistence flow.

## 4. WhatsApp Message Ingress

- [x] 4.1 Migrate `WhatsAppDomainMapper.Result` and `map_message` from `ChatMessageSave` to `ChatMessageRemoteData`.
- [x] 4.2 Preserve WhatsApp message ID, platform timestamp, text/caption composition, attachment-text formatting, and reply message ID.
- [x] 4.3 Migrate `WhatsAppDataResolver.Result` to the complete message domain model.
- [x] 4.4 Replace WhatsApp resolver mutation with explicit remote creation or merge after chat and author resolution.
- [x] 4.5 Migrate WhatsApp existing-message and replied-message lookup plus persistence to `ChatMessageRepository`.
- [x] 4.6 Verify WhatsApp edits preserve composite identity, preserve an existing author only when no new author resolves, replace timestamp/text, and retain reply quoting.
- [x] 4.7 Update WhatsApp mapper and resolver tests for remote/domain inputs, repository results, ordered batches, edits, missing authors, replies, and attachments.
- [x] 4.8 Run focused WhatsApp mapper, resolver, SDK-send, update-responder, chat-agent, and attachment pipeline canaries.
- [x] 4.9 Stop for manual review of WhatsApp message mapping, merge, reply, and persistence flow.

## 5. Outgoing and Shared Message Boundaries

- [x] 5.1 Migrate `DomainLangchainMapper.map_bot_message_to_storage` to produce complete message domain objects with construction-time timestamps and existing generated platform-local message IDs.
- [x] 5.2 Migrate Telegram SDK and shared `PlatformBotSDK` message return type boundaries to complete domain messages while retaining Telegram API-response resolution.
- [x] 5.3 Migrate WhatsApp outgoing API-response storage from `ChatMessageSave`/CRUD conversion to complete domain construction and repository save.
- [x] 5.4 Migrate Telegram and WhatsApp reaction response persistence to complete domain construction and repository save.
- [x] 5.5 Migrate responder and support paths that save or mock outgoing messages to repository/domain types without changing send loops, delays, errors, or notifications.
- [x] 5.6 Update Telegram SDK, WhatsApp SDK, platform SDK, domain-LangChain mapper, and responder tests for domain returns and repository persistence.
- [x] 5.7 Verify text, photo, document, button, reaction, error-response, sent-media attachment, and multi-part response behavior remains unchanged.
- [x] 5.8 Run focused SDK, platform integration, responder, LangChain mapper, attachment, and outgoing message tests.
- [x] 5.9 Stop for manual review of outgoing storage, SDK return types, reactions, and shared message boundaries.

## 6. Cleanup and Broad Consumer Verification

- [x] 6.1 Migrate `CleanupService` old-message deletion to `chat_message_repo.delete_older_than()` without changing attachment-before-message ordering.
- [x] 6.2 Update cleanup tests and support mocks to assert repository deletion counts, failure behavior, and attachment-before-message ordering.
- [x] 6.3 Search non-legacy production and test consumers for remaining CRUD/schema message types and migrate support mocks required by completed boundaries.
- [x] 6.4 Run focused repository, chat agent, integrations, Telegram, WhatsApp, responders, SDKs, attachments, cleanup, and LLM history tests.
- [x] 6.5 Stop for manual review before legacy message persistence deletion.

## 7. Legacy Message Cleanup

- [x] 7.1 Search production and test code for `chat_message_crud`, `ChatMessageCRUD`, `db.schema.chat_message`, `ChatMessageSave`, and `ChatMessage.model_validate`.
- [x] 7.2 Remove legacy `chat_message_crud` type, cache, and property from DI after all production callers migrate.
- [x] 7.3 Migrate chat-message attachment repository tests and remaining database test setup from message CRUD/schema fixtures to message repository/domain fixtures.
- [x] 7.4 Remove obsolete legacy message CRUD/schema tests after domain, mapper, repository, and consumer coverage is accepted.
- [x] 7.5 Remove `src/db/crud/chat_message.py`, `src/db/schema/chat_message.py`, and `SQLUtil.chat_message_crud()` after no callers remain.
- [x] 7.6 Confirm no legacy message CRUD/schema references remain while intentional `ChatMessageDB` references remain only in the model, Alembic registration, attachment cleanup query, mapper, repository, and focused persistence tests.
- [x] 7.7 Run focused repository and all migrated message, attachment, cleanup, platform, and chat consumer tests after legacy deletion.
- [x] 7.8 Stop for manual review before final verification.

## 8. Final Verification

- [x] 8.1 Run `pipenv run pytest`.
- [x] 8.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
- [x] 8.3 Confirm no Alembic migration was generated or required and the database schema is unchanged.
- [x] 8.4 Confirm composite identity, encrypted text, message edits, platform sends, replies, reactions, history ordering, pagination, attachments, cleanup counts, routes, and OpenAPI behavior remain compatible.
- [x] 8.5 Confirm omitted domain timestamps now use construction time and no code depends on the legacy import-time default.
- [x] 8.6 Validate the OpenSpec change with `openspec validate migrate-chat-message-to-repository --strict`.
- [x] 8.7 Summarize the remote/complete state split, timestamp correction, merge semantics, composite-key lifecycle, remaining risks, and completion status for final review.
