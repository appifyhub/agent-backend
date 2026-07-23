## Context

Telegram and WhatsApp currently follow the same broad inbound path: a platform mapper eagerly produces an aggregate containing remote chat, author, message, attachment, and reply data, then another component turns those values into persisted domain objects. Attachment-aware formatting also added a second representation of message content, an initial attachment-free message save, attachment resolution, and a final message save. The Telegram outbound SDK converts successful sends into synthetic inbound updates and routes them back through both layers, while the WhatsApp SDK already persists outbound messages directly.

This change assumes a new or purged database, so it does not need to repair message text written by an older pipeline. Existing repository and service behavior remains authoritative for chat/user merging, membership synchronization, attachment storage and deduplication, message edits, and complete domain persistence. `ChatAgent` remains a post-ingestion consumer of repository-backed history and is not given attachment-loading responsibility.

## Goals / Non-Goals

**Goals:**

- Replace each platform data resolver with a clearly named inbound service that owns the complete raw-update-to-local-result orchestration.
- Keep `TelegramChatInboundService` and `WhatsAppChatInboundService` separate but intentionally similar so their final duplication can be evaluated after implementation.
- Interleave granular platform mapping with the local operation that consumes it instead of producing a complete mapped update before persistence begins.
- Ensure every remote-data mapper result is derived exclusively from the platform payload or platform identity and never from local persistence, formatting, or runtime configuration.
- Resolve authoritative local chat, author, and attachment state before constructing and saving an inbound message.
- Persist each inbound message once and format attachment references only from stored local attachment IDs.
- Preserve author merging, membership creation, agent-message handling, edits, replies, native Telegram quotes, WhatsApp batch ordering, and responder behavior.
- Remove every inbound mapper/resolver dependency from `TelegramBotSDK` and persist Telegram outbound responses directly, matching WhatsApp.

**Non-Goals:**

- Introducing a shared inbound-service base class, protocol, callback framework, or platform switch in this change.
- Changing attachment persistence identity, deduplication, or message ownership semantics.
- Moving attachment lookup or formatting into `ChatAgent`.
- Removing final local attachment references from stored message text.
- Supporting or migrating message text produced by the previous pipeline.
- Adding defensive preflight mapping, transaction coordination, or recovery behavior for a mapping failure after earlier local objects have been stored.
- Requiring remote DTOs to reproduce platform wire models byte-for-byte; transparent type normalization and provider-derived display values remain allowed.
- Changing database schemas, public APIs, OpenAPI documentation, or platform API clients.

## Decisions

### Map platform data at the point of local use

`TelegramDomainMapper` and `WhatsAppDomainMapper` will remain responsible for pure conversion of individual platform values. They will not expose an aggregate `Result` or map an entire update before local storage begins. The inbound services will call granular chat, author, attachment, and message mapping only when the corresponding value is needed.

`TelegramChatInboundService` will select `edited_message` or `message` from the update and ingest that raw message directly. `WhatsAppChatInboundService` will traverse the webhook envelope to collect raw `(Message, Value)` contexts and sort those raw contexts by timestamp before ingesting each message. This envelope traversal and ordering does not create a mapped domain stage.

Keeping the granular mapper operations pure preserves focused payload tests. Keeping the services platform-specific avoids a generic abstraction before the two completed implementations can be compared. A physical mapper/service file merge is not required: the simplification is the removal of the eager phase boundary.

### Map and store each message in dependency order

For each raw platform message, the platform inbound service will:

1. Map the chat, immediately store it through the chat repository, and retain the returned `ChatConfig`.
2. Map the author, immediately store it, detect whether it is the agent, and synchronize membership for real users.
3. For a real author, map remote attachments only at the attachment stage, then convert, download, and store each one using the retained local chat and uploader IDs. For the agent, skip remote attachment mapping and load any local attachments already associated with the message.
4. Map one complete remote message value directly from the raw platform message, including its identity, original send time, human-authored text or caption, explicit `replied_to_message_id`, and native selected quote text where supported.
5. Format the final local message text from that remote human text, native platform quote content, resolved stored reply, and retained local attachment references.
6. Merge the unchanged remote message metadata into any existing local message, assign the separately formatted local text, and store the complete `ChatMessage` once.
7. Return the retained local chat, author, message, and attachments to the responder.

Inbound platform message IDs are known before attachment persistence and will be assigned to attachment drafts immediately. Only outbound media needs a later attachment `message_id` update because its platform message ID is unknown until the send succeeds.

### Keep remote mapper output provenance-pure

Remote DTOs are provider-neutral projections rather than byte-for-byte platform wire models. They may normalize remote values into domain-friendly types, such as converting an epoch timestamp to `datetime`, converting an integer identity to `str`, joining remote first and last names, or deriving a display value exclusively from provider fields. They must not accept or return values obtained from repositories, locally stored objects, message formatting, application configuration, or synthesized transport URLs.

`ChatMessageRemoteData` will include the remote message text, explicit replied-message identity, and optional native selected quote text. `map_message()` will accept only the raw platform message and will populate those fields directly. The separate mapper operations that return `FormattedChatMessage` or only a replied-message ID will be removed. Telegram `sent_at` will use the provider's original `date`; `edit_date` will not be substituted for a field whose meaning is send time.

The inbound service will retain `ChatMessageRemoteData` unchanged. It will build `FormattedChatMessage` from the remote text plus stored reply and attachment state, then pass both the remote data and separately formatted text to `store_message()`. Consequently, local attachment IDs, database reply text, and quote markers will exist only on the local `ChatMessage`, while `raw_message_text` will come directly from the remote message value.

Telegram attachment mapping will read the actual media payload fields directly instead of manufacturing a `File` response model. It will not import configuration or synthesize an authenticated file URL. `TelegramBotAPI.download_file()` remains responsible for calling `getFile`, resolving the current provider path, constructing the transport URL, and downloading bytes. A remote attachment URL remains absent when the inbound payload does not supply one.

For WhatsApp, `message.from_` remains the authoritative sender and chat identity. Optional profile metadata will be used only from a contact whose `wa_id` matches `message.from_`; an unrelated first contact cannot replace the sender identity or chat title.

Telegram `telegram_chat_id` is a user's private delivery address, not the author's platform identity. The Telegram mapper will include it only when a private `message.chat.id` matches `message.from_user.id`, proving that the private chat belongs to that author. User merging will fill this address when it is missing and will not replace an existing non-null address. The inbound service therefore needs no agent-specific mutation of mapped author data. WhatsApp has no separate chat-address field: `message.from_` is already both the authoritative sender and private chat identity, so no equivalent clearing or merge exception is required.

### Use only authoritative local attachment IDs in stored message text

Mappers will produce base message content without attachment reference text. After attachment storage and deduplication, the inbound service will format the final attachment reference from the returned local attachment objects. No temporary or remote attachment ID will enter newly stored message text.

The final `📎 [ ... ]` reference remains part of stored message text because existing chat-history mapping exposes attachment IDs to the model through that text. `ChatAgent` will continue loading messages through the repository and will not perform separate attachment queries.

Because deployment assumes a purged database, quoted replies can use the already-canonical stored replied-message text directly. There is no runtime compatibility path that parses or replaces historical remote attachment references.

### Preserve current author, edit, reply, and agent behavior

Existing user mapping and waitlist defaults will remain unchanged. Agent membership exclusion remains in each inbound service, while Telegram private chat ownership is enforced by the mapper and shared user merge rule rather than an agent-specific persistence workaround.

Existing-message updates will continue using the remote-data merge behavior so a resolved author replaces the stored author, a missing resolved author preserves the stored non-null author, and platform metadata plus separately formatted local text are applied. Telegram edits retain the original send timestamp rather than replacing it with the edit timestamp.

WhatsApp raw message contexts will be processed oldest-first so a later message can reply to an earlier message in the same update. A known replied message will be prefixed using the existing quote-depth convention; an unknown replied message will be logged and will not prevent the current message from being stored.

Agent-authored inbound updates will not download or duplicate platform attachments that were already archived by the outbound SDK. When local attachments already belong to the message, final formatting will retain those authoritative local references.

### Keep response generation outside inbound services

The Telegram and WhatsApp update responders will call their platform inbound service, receive complete local results, select the actionable result using current platform behavior, inject its author and chat into DI, and then construct `ChatAgent`.

The inbound result will retain the mapped raw message text needed for command, mention, and dispatch decisions separately from the stored text augmented with resolved reply content. `ChatAgent` will continue loading persisted conversation history itself, preserving debounce and burst behavior.

### Keep inbound media download on low-level API clients

`TelegramChatInboundService` will call `TelegramBotAPI.download_file()`, and `WhatsAppChatInboundService` will call `WhatsAppBotAPI.download_media()`. The higher-level SDKs will not gain pass-through download methods and will not be dependencies of inbound services.

This preserves the existing transport boundary and avoids coupling inbound ingestion to outbound send-and-store orchestration.

### Persist Telegram outbound responses directly

Telegram SDK send methods will receive local chat context, call `TelegramBotAPI`, construct a complete `ChatMessage` from the returned platform identity/timestamp plus the known local author and content, and save it through the message repository. Photo and document content will be formatted from the already-stored local attachment, after which that attachment will be updated with the returned platform message ID.

`PlatformBotSDK` and direct Telegram callers will supply the resolved `ChatConfig`, aligning Telegram with the existing WhatsApp SDK boundary. `TelegramBotSDK` will no longer create a synthetic `Update` or call a platform mapper or inbound service.

### Preserve parallel service shape for a later merge assessment

The two inbound services and their focused tests will use the same method ordering, result field ordering, naming where platform semantics match, and scenario coverage. Platform-specific code will remain direct rather than hidden behind hooks. After both implementations are complete and verified, the task includes comparing the concrete duplication and documenting whether a shared service would reduce code without adding indirection.

The completed result for one ingested platform message is genuinely platform-independent and will use a shared `IngestedChatMessage` dataclass containing the stored chat, optional author, stored message, stored attachments, and unformatted remote message text. This shares only the output contract, not orchestration. It is intentionally named for one message rather than one update because a WhatsApp update can produce multiple results.

## Risks / Trade-offs

- [Separate platform services retain some duplicated orchestration] → Keep their structure and tests parallel, then assess a shared implementation from concrete code after the change is complete.
- [Just-in-time mapping or later message storage can fail after chat, user, or attachment state has already been stored] → Let the exception propagate to the responder's existing error logging; Telegram and WhatsApp payloads are stable, and defensive preflight or transaction redesign is outside this change.
- [Changing Telegram SDK methods to require local chat context affects multiple callers] → Update `PlatformBotSDK`, responders, scheduled senders, and focused mocks together, and verify every call site by repository-wide search.
- [Removing remote attachment references changes mapper test expectations] → Replace them with assertions that mapping is attachment-text-free and inbound-service results contain final local references.
- [Agent-authored platform updates could overwrite direct outbound content] → Reuse locally associated attachments and preserve authoritative local references when merging an existing agent message.
- [Separating remote text from formatted local text changes message-mapper and storage signatures] → Update both platform services and focused mapper tests together, and assert that mapper output contains no local enrichment.
- [WhatsApp webhook values can contain multiple contacts] → Match optional contact metadata by the authoritative `message.from_` identity and ignore unrelated contacts.

## Migration Plan

No data migration is required because deployment assumes a purged database. Deploy the mapper, inbound-service, DI, responder, SDK, and test changes together. Rollback restores the previous data resolver and Telegram synthetic-update path.

## Open Questions

None. Whether to merge the two inbound services will be evaluated from their completed implementations rather than decided in this proposal.
