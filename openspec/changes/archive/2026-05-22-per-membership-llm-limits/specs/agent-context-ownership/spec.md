## ADDED Requirements

### Requirement: ChatAgent fetches its own message history
The `ChatAgent` SHALL fetch chat messages internally via DI using `membership.max_chat_history_depth` as the limit, instead of receiving pre-fetched messages from the responder. When membership is unavailable, it SHALL fall back to `config.chat_history_depth`.

#### Scenario: Agent fetches messages using membership depth
- **WHEN** a ChatAgent is created for a user with `max_chat_history_depth=15`
- **THEN** the agent SHALL fetch at most 15 recent messages from the chat message CRUD

#### Scenario: Fallback to global config when no membership
- **WHEN** a ChatAgent is created and membership is not available
- **THEN** the agent SHALL fetch at most `config.chat_history_depth` recent messages

### Requirement: ChatAgent fetches its own attachments
The `ChatAgent` SHALL fetch message attachments internally for the messages it retrieved, instead of receiving pre-fetched attachment IDs from the responder.

#### Scenario: Attachments fetched for retrieved messages only
- **WHEN** the agent fetches 15 messages based on membership depth
- **THEN** attachments SHALL be fetched only for those 15 messages, not for any messages outside that window

### Requirement: ChatAgent constructor simplified
The `ChatAgent` constructor SHALL accept `raw_last_message`, `last_message_id`, `configured_tool`, and `di` — dropping the `messages` and `attachment_ids` parameters.

#### Scenario: Responder creates ChatAgent without message prefetch
- **WHEN** a Telegram or WhatsApp responder creates a ChatAgent
- **THEN** it SHALL pass only `raw_last_message`, `last_message_id`, `configured_tool`, and `di`
- **THEN** the responder SHALL NOT fetch messages or attachments itself

### Requirement: Responders no longer fetch messages
Both `TelegramUpdateResponder` and `WhatsAppUpdateResponder` SHALL NOT contain message-fetching or attachment-fetching logic. That responsibility SHALL belong entirely to `ChatAgent`.

#### Scenario: Telegram responder delegates to ChatAgent
- **WHEN** a Telegram update is received
- **THEN** the responder SHALL resolve domain data, inject invoker/chat, create ChatAgent, and call execute — without fetching messages or attachments

#### Scenario: WhatsApp responder delegates to ChatAgent
- **WHEN** a WhatsApp update is received
- **THEN** the responder SHALL resolve domain data, inject invoker/chat, create ChatAgent, and call execute — without fetching messages or attachments
