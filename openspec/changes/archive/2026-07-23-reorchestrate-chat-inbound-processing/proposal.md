## Why

Telegram and WhatsApp currently resolve inbound data through staged remote, formatted, and local message representations. Even after removing temporary attachment references, duplicate message writes, and eager aggregate mapping, the message mappers still accept locally formatted text and return it as remote data. Reorchestrating each platform's inbound path around just-in-time mapping, truthful remote-data contracts, and dependency-ordered local storage keeps provider facts distinct from local formatting and persistence.

## What Changes

- Replace the Telegram and WhatsApp data resolvers with separate `TelegramChatInboundService` and `WhatsAppChatInboundService` orchestrators that remain structurally parallel without introducing a shared base class.
- Keep granular platform payload interpretation in the Telegram and WhatsApp domain mappers, but remove their aggregate update result contracts and call each mapping operation only when its local result is ready to be stored.
- Make every remote mapper result derivable exclusively from the platform payload or platform identity: message mapping accepts only the raw platform message and retains remote text, reply identity, native quote text, and original send time without local attachment IDs, stored reply text, formatting, configuration, or synthesized URLs.
- Map, store, and retain the local chat, author, membership, and attachments in dependency order before constructing and storing the final local message.
- Construct formatted message text only in the inbound service, then store that local text separately from the unchanged remote message data.
- Map Telegram attachment metadata directly from the actual media payload and resolve authenticated file URLs only inside `TelegramBotAPI`; match WhatsApp contact metadata to the message's actual sender instead of assuming the first contact is authoritative.
- Associate a Telegram private chat address with an author only when the remote chat and author identities match, and fill a missing stored address without overwriting an existing one.
- Build stored attachment references only from authoritative local attachment IDs and persist each inbound message once, preserving replies, edits, agent-authored behavior, attachment deduplication, and WhatsApp batch ordering.
- Return the resolved local chat, author, message, and attachments to the platform responder, which continues to invoke `ChatAgent` after ingestion.
- Represent each successfully ingested platform message with one shared `IngestedChatMessage` contract while keeping platform orchestration separate.
- Make Telegram outbound persistence direct, matching WhatsApp: store the sent local message from known chat context and the API response without routing it through inbound mapping or resolution.
- Keep inbound platform media downloads on the low-level Telegram and WhatsApp API clients; the outbound SDKs do not participate in inbound ingestion.

## Capabilities

### New Capabilities

- `chat-inbound-processing`: Dependency-ordered Telegram and WhatsApp inbound ingestion that persists authoritative local entities before handing a stored message to response processing.

### Modified Capabilities

## Impact

- `src/features/chat/telegram/` and `src/features/chat/whatsapp/`: replace data resolvers with platform-specific inbound services, remove aggregate mapper results, keep mapper outputs remote-provenance-pure, and interleave granular mapping with local storage.
- `ChatMessageRemoteData` and its mapper tests: represent remote message text, reply identity, native quote text, and original send time without accepting locally enriched text.
- `src/features/chat/telegram/sdk/telegram_bot_sdk.py`: remove inbound mapper/resolver dependencies and persist outbound messages directly.
- `src/features/chat/whatsapp/sdk/whatsapp_bot_sdk.py`: retain direct outbound persistence and align parallel behavior where needed.
- `src/features/integrations/platform_bot_sdk.py`, DI wiring, and platform update responders: route through local chat context and the new inbound services.
- Focused mapper, inbound-service, SDK, responder, message-formatting, edit, reply, and attachment tests will be updated while preserving existing user-visible behavior.
- No database migration, legacy-data compatibility path, public API change, API documentation change, or new dependency is expected.
