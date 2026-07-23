## ADDED Requirements

### Requirement: Platform data is mapped at the point of local use
The system SHALL map Telegram and WhatsApp payload values only when the inbound service is ready to consume them, without producing an aggregate mapped-update result or formatting message attachment references from remote attachment IDs.

#### Scenario: Telegram message is ingested
- **WHEN** a Telegram update contains a supported message
- **THEN** the inbound service selects the raw message and maps its chat, author, attachments, and complete remote message data only at their respective storage steps
- **THEN** no aggregate Telegram mapper result is created
- **THEN** stored message text contains no attachment reference derived from a Telegram file ID

#### Scenario: WhatsApp messages are ingested
- **WHEN** a WhatsApp update contains one or more supported messages
- **THEN** the inbound service enumerates raw message and value contexts and sorts them by raw message timestamp
- **THEN** it maps each message's chat, author, attachments, and complete remote message data only at their respective storage steps
- **THEN** no aggregate WhatsApp mapper results are created
- **THEN** stored message text contains no attachment reference derived from a WhatsApp media ID

### Requirement: Remote mapper results contain only provider-derived data
Telegram and WhatsApp domain mappers SHALL return remote DTO values derived exclusively from their raw platform payloads or known platform identity, without accepting locally enriched values or reading local persistence, message formatting, application configuration, or synthesized transport URLs.

#### Scenario: Remote message data is mapped
- **WHEN** a platform mapper maps a raw inbound message
- **THEN** message mapping accepts only the raw platform message and any raw platform context required to interpret it
- **THEN** the returned remote message data contains the platform message identity, original send time, human-authored text or caption, explicit replied-message identity, and native selected quote text where supported
- **THEN** it contains no stored reply text, local attachment ID, attachment marker, or other locally formatted text

#### Scenario: Telegram edit is mapped
- **WHEN** a Telegram payload contains both the original message date and an edit date
- **THEN** remote `sent_at` is derived from the original message date
- **THEN** the edit date is not represented as the message send time

#### Scenario: Telegram attachment metadata is mapped
- **WHEN** a Telegram message contains supported media metadata
- **THEN** the mapper derives the remote attachment identity, message identity, size, and MIME type directly from that media payload
- **THEN** it does not manufacture a Telegram file-response model
- **THEN** it does not synthesize or persist an authenticated download URL from application configuration

#### Scenario: WhatsApp sender metadata is mapped
- **WHEN** a WhatsApp value contains contacts for one or more identities
- **THEN** `message.from_` remains the authoritative author and chat identity
- **THEN** optional profile metadata is taken only from the contact whose `wa_id` matches `message.from_`
- **THEN** an unrelated first contact does not replace the sender identity or chat title

#### Scenario: Telegram private chat belongs to the author
- **WHEN** a Telegram private message's chat identity matches its author identity
- **THEN** the mapper includes that private chat identity as the author's Telegram chat address

#### Scenario: Telegram private chat does not belong to the author
- **WHEN** a Telegram private message's chat identity differs from its author identity
- **THEN** the mapper does not associate that chat address with the author
- **THEN** the inbound service does not mutate mapped author data to compensate for persistence behavior

#### Scenario: Existing Telegram chat address is merged
- **WHEN** remote author data resolves an existing user with a non-null Telegram chat address
- **THEN** user merging preserves the existing address
- **THEN** a remote Telegram chat address fills the field only when the existing address is missing

### Requirement: Local message formatting remains outside remote mappers
Each inbound service SHALL construct local formatted message text from unchanged remote message data and authoritative local reply and attachment state.

#### Scenario: Inbound message is formatted and stored
- **WHEN** remote message data and its retained local attachments are available
- **THEN** the inbound service formats native quote text, resolved stored reply text, and local attachment references outside the platform mapper
- **THEN** it stores the formatted text on the local `ChatMessage`
- **THEN** it does not replace or mutate the remote message text with that formatted local text
- **THEN** the inbound result exposes the unchanged remote human-authored text as `raw_message_text`

### Requirement: Each platform has a dedicated inbound orchestration service
The system SHALL ingest Telegram updates through `TelegramChatInboundService` and WhatsApp updates through `WhatsAppChatInboundService` without a shared inbound-service base class.

#### Scenario: Telegram responder ingests an update
- **WHEN** the Telegram responder receives a supported update
- **THEN** it delegates mapping and local persistence to `TelegramChatInboundService`
- **THEN** the service returns a complete local result for the ingested message

#### Scenario: WhatsApp responder ingests an update
- **WHEN** the WhatsApp responder receives an update containing supported messages
- **THEN** it delegates mapping and local persistence to `WhatsAppChatInboundService`
- **THEN** the service returns complete local results for all ingested messages

#### Scenario: Platform implementations remain independently inspectable
- **WHEN** the two inbound services implement equivalent orchestration behavior
- **THEN** their platform-specific mapping, download, and agent handling remain explicit
- **THEN** no inheritance or callback abstraction hides those differences

#### Scenario: Platform message ingestion completes
- **WHEN** either inbound service successfully ingests one platform message
- **THEN** it returns an `IngestedChatMessage` containing the stored chat, optional author, stored message, stored attachments, and unformatted remote message text
- **THEN** Telegram and WhatsApp use the same result contract without sharing their orchestration

### Requirement: Inbound services resolve local dependencies before messages
Each inbound service SHALL map, store, and retain authoritative local chat, author, membership, and attachment state before constructing the final local message.

#### Scenario: Real user sends an attachment message
- **WHEN** a raw platform message has a real author and one or more platform attachments
- **THEN** the service maps, stores, and retains the local chat
- **THEN** it maps and stores the local author and synchronizes chat membership
- **THEN** it maps, downloads, and stores each attachment with the local chat ID, uploader ID, and already-known platform message ID
- **THEN** it retains the authoritative attachment returned by attachment storage and deduplication

#### Scenario: Attachment has no resolvable uploader
- **WHEN** a non-agent platform message contains an attachment but no local author can be stored
- **THEN** inbound attachment persistence fails with the platform mapping error behavior
- **THEN** no final local message containing unresolved attachment references is saved

#### Scenario: Message has no attachments
- **WHEN** a platform message contains no attachments
- **THEN** the service proceeds from chat and author resolution directly to final message construction

### Requirement: Inbound messages use final local attachment references
The system SHALL construct and persist each inbound message only after its retained attachments have authoritative local IDs.

#### Scenario: New attachment message is stored
- **WHEN** attachment storage returns local attachments for a mapped message
- **THEN** final message text references only those local attachment IDs and resolved MIME types
- **THEN** no Telegram file ID or WhatsApp media ID is used as a temporary message-text attachment reference
- **THEN** the message repository saves the complete message once

#### Scenario: Deduplicated attachment is returned
- **WHEN** attachment persistence resolves an existing local attachment under current deduplication rules
- **THEN** final message text uses the ID and metadata of the returned local attachment

#### Scenario: Message is stored without attachments
- **WHEN** a mapped message has no retained local attachments
- **THEN** final message text contains no attachment reference

### Requirement: Inbound edit and reply behavior is preserved
The inbound services SHALL preserve existing platform message edit, quote, reply, and batch-order behavior while saving final local messages.

#### Scenario: Existing message has a newly resolved author
- **WHEN** mapped remote data matches an existing message and resolves a local author
- **THEN** the service preserves the message composite identity
- **THEN** it replaces the stored author with the resolved author and applies the original platform send time and separately formatted local text

#### Scenario: Existing message has no newly resolved author
- **WHEN** mapped remote data matches an existing message without resolving a local author
- **THEN** the service preserves the existing non-null author
- **THEN** it applies the original platform send time and separately formatted local text

#### Scenario: Message replies to a known stored message
- **WHEN** a mapped message identifies a replied message that exists in the same local chat
- **THEN** the service prefixes the stored replied-message text using the established full-reply quote depth
- **THEN** the current message content and final local attachment references remain present

#### Scenario: Message replies to an unknown message
- **WHEN** the replied-message identity is not found in the local chat
- **THEN** the service logs the missing reply
- **THEN** it stores the current message without synthesized reply text

#### Scenario: Telegram provides native quote content
- **WHEN** a Telegram message contains native selected quote text
- **THEN** the stored message preserves that text using the established native-quote depth

#### Scenario: WhatsApp update contains multiple messages
- **WHEN** a WhatsApp update contains multiple supported messages
- **THEN** the inbound service processes their raw message contexts oldest-first
- **THEN** a later message can resolve an earlier message from the same update as its reply

### Requirement: Agent-authored inbound data avoids duplicate attachment ingestion
The inbound services SHALL preserve agent identity behavior without redownloading attachments already archived by outbound delivery.

#### Scenario: Agent-authored message contains platform attachment metadata
- **WHEN** the mapped author identifies the configured platform agent
- **THEN** the service skips membership synchronization for that author
- **THEN** it does not download or persist duplicate platform attachment bytes

#### Scenario: Existing agent message has local attachments
- **WHEN** an agent-authored platform update matches a locally stored outbound message with associated attachments
- **THEN** the service identifies the agent before the attachment stage and skips remote attachment mapping
- **THEN** final stored content retains authoritative local attachment references
- **THEN** remote attachment IDs do not replace those references

#### Scenario: Telegram agent is resolved
- **WHEN** Telegram mapping identifies the configured agent
- **THEN** a target chat whose identity differs from the agent identity is not mapped as the agent's private Telegram chat ID

### Requirement: Responders invoke the chat agent after inbound persistence
Platform responders SHALL invoke response processing only from complete inbound-service results while preserving current platform selection behavior.

#### Scenario: Telegram message is actionable
- **WHEN** Telegram inbound ingestion returns a result with a local author
- **THEN** the responder injects the returned author and chat into DI
- **THEN** it invokes `ChatAgent` using the mapped raw message text and stored message ID

#### Scenario: WhatsApp batch is actionable
- **WHEN** WhatsApp inbound ingestion returns one or more results with local authors
- **THEN** the responder selects the latest result by stored message timestamp
- **THEN** it injects that result's author and chat and invokes `ChatAgent` once

#### Scenario: Inbound message has no author
- **WHEN** inbound ingestion returns no actionable result with a local author
- **THEN** the responder does not invoke `ChatAgent`

#### Scenario: Chat history is prepared
- **WHEN** `ChatAgent` runs after inbound persistence
- **THEN** it continues loading complete persisted message history through existing repositories
- **THEN** it is not responsible for downloading or separately resolving message attachments

### Requirement: Outbound SDK persistence is independent from inbound services
Telegram and WhatsApp SDK send paths SHALL persist successful outbound messages directly from known local context and platform API responses.

#### Scenario: Telegram sends text or button content
- **WHEN** the Telegram API successfully returns a sent message
- **THEN** `TelegramBotSDK` constructs and saves a complete local message using the resolved local chat and configured agent author
- **THEN** it does not create a synthetic update or call a platform mapper or inbound service

#### Scenario: Telegram sends retained media
- **WHEN** the Telegram API successfully sends a stored local attachment
- **THEN** the SDK saves message text using the attachment's local ID
- **THEN** it updates the attachment with the returned platform message ID
- **THEN** it does not redownload or deduplicate the attachment through inbound ingestion

#### Scenario: WhatsApp sends content
- **WHEN** the WhatsApp API successfully returns a sent message
- **THEN** `WhatsAppBotSDK` continues constructing and saving the complete local message directly

#### Scenario: Inbound service downloads platform media
- **WHEN** an inbound service needs Telegram or WhatsApp attachment bytes
- **THEN** it calls the corresponding low-level platform API client
- **THEN** it does not call the outbound platform SDK
