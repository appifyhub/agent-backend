## Purpose

Route chat agent error details to the user's private chat with a clickable settings link, keeping the originating chat clean with only an emoji reaction.

## ADDED Requirements

### Requirement: Private chat error delivery

When the chat agent encounters any error during message processing, and the user has a known private chat with the bot, the error details and a settings link are sent to that private chat. The originating chat receives only the error emoji.

#### Scenario: User has a private chat
- **WHEN** an error occurs in `ChatAgent.execute()` or `ChatAgent.process_commands()` and the user has a resolvable private chat ID
- **THEN** the originating chat receives only the error emoji (e.g. "🤯") as the reply
- **AND** the user's private chat receives the full error message with error code
- **AND** the user's private chat receives a clickable settings button link

#### Scenario: User has no private chat
- **WHEN** an error occurs and the user has no resolvable private chat ID
- **THEN** the originating chat receives the full error text with "Check settings" copy (current behavior with updated wording)

#### Scenario: Private chat delivery fails
- **WHEN** the private chat send (error details or settings link) fails for any reason
- **THEN** a warning is logged
- **AND** the failure is silently swallowed — no error propagates to the caller
- **AND** the originating chat still receives the emoji-only reply

### Requirement: Updated fallback copy

The fallback error message text when no private chat is available uses "Check settings" instead of "Open /settings".

#### Scenario: Fallback error text
- **WHEN** no private chat is available and the error is rendered as text in the originating chat
- **THEN** the message footer reads "Check settings" instead of "Open /settings"
