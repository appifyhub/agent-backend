## 1. Simplify mapped inbound content

- [x] 1.1 Update the Telegram and WhatsApp mapper result contracts to retain raw message content, attachment metadata, and reply identity without a second formatted-message representation.
- [x] 1.2 Stop both mappers from generating attachment reference text from remote platform IDs while preserving captions, text, native Telegram quotes, timestamps, and message identities.
- [x] 1.3 Simplify shared message-formatting utilities so final attachment references are built only from local `ChatAttachment` objects and stored reply text can be prefixed at the established quote depths.
- [x] 1.4 Update focused mapper and formatting tests to prove mapped content contains no remote attachment reference and final formatting uses local attachment IDs.

## 2. Add platform inbound services

- [x] 2.1 Replace `TelegramDataResolver` with `TelegramChatInboundService`, preserving chat/user merging, Telegram agent handling, membership synchronization, attachment download through `TelegramBotAPI`, edit merging, reply formatting, and a single final message save.
- [x] 2.2 Replace `WhatsAppDataResolver` with `WhatsAppChatInboundService`, preserving the same orchestration order, WhatsApp agent handling, attachment download through `WhatsAppBotAPI`, edit merging, reply formatting, oldest-first batch processing, and a single final message save.
- [x] 2.3 Ensure each inbound result returns its resolved local chat, author, message, and attachments together with the mapped raw message text required by responder dispatch logic.
- [x] 2.4 Preserve agent-authored message behavior by skipping duplicate media download and retaining any local attachments already associated with a directly persisted outbound message.
- [x] 2.5 Replace the existing resolver tests with parallel Telegram and WhatsApp inbound-service behavior tests covering allowed dependency order, no-author media failure, deduplication results, edits, replies, native quotes, agent messages, and batch ordering.

## 3. Integrate inbound services with responders

- [x] 3.1 Replace data-resolver DI properties and cached fields with the two inbound-service dependencies and remove all production references to the old resolver classes.
- [x] 3.2 Update Telegram and WhatsApp update responders to ingest through their platform service, retain current actionable-message selection, inject resolved local context, and invoke `ChatAgent` with raw message text only after persistence.
- [x] 3.3 Update responder tests to verify mapping and persistence are delegated to the inbound service and existing no-message, no-author, reaction, response, and error-notification behavior remains unchanged.

## 4. Decouple outbound SDK persistence

- [x] 4.1 Change Telegram SDK send-and-store paths to accept resolved local chat context, persist complete outbound messages directly from Telegram API responses, and remove synthetic updates plus mapper/inbound-service dependencies.
- [x] 4.2 Format Telegram outbound photo and document messages from their local attachments and update each attachment with the returned platform message ID after the send succeeds.
- [x] 4.3 Update `PlatformBotSDK` and every direct Telegram caller to supply the resolved `ChatConfig`, while preserving target-chat lookup for private buttons, scheduled sends, and other scoped sends.
- [x] 4.4 Update Telegram SDK and shared platform SDK tests to prove direct persistence, local attachment references, later outbound attachment association, and the absence of inbound-service calls; retain equivalent WhatsApp direct-persistence coverage.

## 5. Verify behavior and assess later consolidation

- [x] 5.1 Run Ruff and the spacing checker on every changed Python file and fix only issues introduced by this change.
- [x] 5.2 Run focused mapper, formatting, inbound-service, SDK, responder, attachment, and chat-agent tests through Pipenv.
- [x] 5.3 Run the full test suite through Pipenv and verify repository-wide searches find no old data-resolver references or remote attachment-reference construction.
- [x] 5.4 Compare the completed Telegram and WhatsApp inbound services and report the concrete shared flow, platform-only branches, and estimated effort of a later merge without merging them in this change.

## 6. Remove the eager mapping phase

- [x] 6.1 Remove the aggregate `Result` contracts and `map_update()` methods from `TelegramDomainMapper` and `WhatsAppDomainMapper`, retaining only granular platform conversion operations used at the point of local storage.
- [x] 6.2 Rework `TelegramChatInboundService` to ingest the raw selected Telegram message directly, map and store each local object in dependency order, remove `resolve(mapping_result)`, and use `ingest`/`store` naming for orchestration and persistence helpers.
- [x] 6.3 Rework `WhatsAppChatInboundService` to enumerate and sort raw `(Message, Value)` contexts before ingesting each message, map and store each local object in dependency order, remove `resolve_all(mapping_results)` and `resolve(mapping_result)`, and use parallel `ingest`/`store` naming.
- [x] 6.4 Map base content and the explicit `replied_to_message_id` only after attachment storage, then construct and store the complete final message once while returning the unaugmented mapped content as `raw_message_text`.
- [x] 6.5 Update mapper, inbound-service, DI, responder, and SDK tests to remove aggregate mapper-result fixtures and prove just-in-time mapping, oldest-first raw WhatsApp processing, agent attachment skipping, preserved edits/replies, and unchanged outbound isolation.
- [x] 6.6 Run Ruff and the spacing checker on changed Python files, run focused and full tests through Pipenv, and verify repository-wide searches find no aggregate mapper result or old resolver references.

## 7. Keep remote mapper output provenance-pure

- [x] 7.1 Extend `ChatMessageRemoteData` with explicit replied-message identity and optional native quote text, then make both platform `map_message()` methods derive the complete value from only the raw platform message.
- [x] 7.2 Remove mapper `FormattedChatMessage` construction and separate reply-identity mapping; use the original Telegram message date for `sent_at` instead of substituting its edit date.
- [x] 7.3 Map Telegram attachment DTOs directly from actual media payload fields without dummy `File` models, application configuration, bot tokens, or synthesized download URLs, while retaining download resolution in `TelegramBotAPI`.
- [x] 7.4 Keep `message.from_` authoritative in WhatsApp author and chat mapping, and use optional profile metadata only from the matching `wa_id` contact.
- [x] 7.5 Update both inbound services to retain unchanged remote message data, construct all quote, stored-reply, and local-attachment formatting locally, and pass separately formatted text into `store_message()`.
- [x] 7.6 Add parallel mapper and inbound-service tests proving remote-output provenance, original Telegram send time on edits, matching WhatsApp contacts, absent synthesized Telegram URLs, unchanged raw message text, and preserved local formatted storage.
- [x] 7.7 Run Ruff and the spacing checker on changed Python files, run focused and full tests through Pipenv, and verify repository-wide searches find no mapper imports of local message-formatting or Telegram configuration modules.

## 8. Keep private chat addresses author-owned

- [x] 8.1 Map a Telegram private chat address only when its remote chat identity matches the remote author identity, and remove the inbound service's agent-specific mapped-author mutation.
- [x] 8.2 Make user remote-data merging fill a missing Telegram chat address without replacing an existing non-null address; confirm WhatsApp needs no separate chat-address rule.
- [x] 8.3 Align concise dependency-order comments across both platform `ingest_message()` implementations.
- [x] 8.4 Update focused mapper, user-mapper, and inbound-service tests, then run lint, spacing, focused tests, the full suite, residue checks, and strict OpenSpec validation.

## 9. Share the ingested-message result

- [x] 9.1 Extract the identical nested service result dataclasses into one platform-independent `IngestedChatMessage` contract.
- [x] 9.2 Update both inbound services, responders, and existing tests to use the shared contract without introducing shared orchestration.
- [x] 9.3 Run lint, spacing, focused tests, the full suite, nested-result residue checks, and strict OpenSpec validation.
