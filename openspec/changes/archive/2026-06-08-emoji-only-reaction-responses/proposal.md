## Why

Short chat acknowledgements from the agent currently become new text messages even when an emoji reaction would be the natural platform-native response. This adds noise to Telegram and WhatsApp chats and makes future chat history less clear about whether the user request was resolved.

## What Changes

- Allow the chat model to reply with exactly one platform-supported reaction emoji when a lightweight acknowledgement is enough.
- Detect exact emoji-only responses with `is_reaction_response(...)` based on chat type.
- For Telegram and WhatsApp, send a reaction to the incoming message instead of sending the emoji as a new text message.
- Store a synthetic bot-authored chat history message using `<reaction>{emoji}</reaction>` so future replies can see that the agent responded.
- Add release-summary prompt constraints: do not use code blocks unless actual code is included, and do not mention or reference the current user or current chat.

## Capabilities

### New Capabilities

- `chat-reaction-responses`: Change-local requirements for converting emoji-only chat responses into platform reactions.

### Modified Capabilities

- None.

## Impact

- `src/features/integrations/integrations.py`
- `src/features/integrations/prompt_resolvers.py`
- `src/features/prompting/prompt_composer.py`
- `src/features/prompting/prompt_library.py`
- `src/features/chat/telegram/telegram_update_responder.py`
- `src/features/chat/whatsapp/whatsapp_update_responder.py`
- Existing responder and integrations tests
