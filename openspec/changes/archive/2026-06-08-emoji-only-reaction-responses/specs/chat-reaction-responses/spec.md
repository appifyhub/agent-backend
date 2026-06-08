## ADDED Requirements

### Requirement: Emoji-only chat responses become platform reactions
The system SHALL treat an agent chat response containing exactly one allowed platform reaction emoji as a reaction response for chat types that support reactions.

#### Scenario: Telegram reaction response
- **WHEN** a Telegram chat response contains exactly one allowed Telegram reaction emoji
- **THEN** the system sends that emoji as a reaction to the incoming Telegram message
- **AND** the system does not send the emoji as a new Telegram text message

#### Scenario: WhatsApp reaction response
- **WHEN** a WhatsApp chat response contains exactly one allowed WhatsApp reaction emoji
- **THEN** the system sends that emoji as a reaction to the incoming WhatsApp message
- **AND** the system does not send the emoji as a new WhatsApp text message

#### Scenario: Unsupported chat type
- **WHEN** a chat type has no allowed reaction list
- **THEN** the system does not classify emoji-only responses as reaction responses for that chat type

### Requirement: Reaction responses are stored in chat history
The system SHALL store classified reaction responses as bot-authored synthetic chat messages using the `<reaction>{emoji}</reaction>` marker format.

#### Scenario: Reaction response is stored
- **WHEN** the system classifies an agent response as a reaction response
- **THEN** the system stores a chat message with ID `reaction:{incoming_message_id}`
- **AND** the stored text uses `<reaction>{emoji}</reaction>`

#### Scenario: Platform reaction failure is ignored
- **WHEN** storing the reaction response succeeds
- **AND** the platform reaction API fails
- **THEN** the system does not send an error response to the chat
- **AND** the stored reaction history message remains available for future chat context

### Requirement: Chat prompt exposes allowed reaction responses
The system SHALL include platform-specific allowed reaction emojis in the chat system prompt and instruct the model to use exactly one of them when a lightweight acknowledgement is enough.

#### Scenario: Platform reactions are available in prompt
- **WHEN** the chat prompt is built for a supported reaction platform
- **THEN** the prompt includes the allowed reaction emoji list for that platform
- **AND** the prompt instructs that reaction-only output must contain exactly one emoji and no additional text
