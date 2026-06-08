## 1. Reaction Classification

- [x] 1.1 Add platform-specific allowed reaction resolution for Telegram and WhatsApp.
- [x] 1.2 Add `is_reaction_response(text, chat_type)` as a simple exact trimmed-string check.
- [x] 1.3 Ensure unsupported chat types, including GitHub, do not classify emoji-only content as reaction responses.

## 2. Prompt Updates

- [x] 2.1 Add `allowed_reactions` as a prompt variable.
- [x] 2.2 Include the platform-specific allowed reaction list in chat prompts.
- [x] 2.3 Instruct the chat model to prefer a single allowed reaction emoji over one- or two-word acknowledgements when appropriate.
- [x] 2.4 Update release-summary prompt guidance to avoid code blocks unless actual code is included.
- [x] 2.5 Update release-summary prompt guidance to avoid referencing the current user or current chat.

## 3. Responder Behavior

- [x] 3.1 In Telegram response delivery, branch inline on `is_reaction_response(...)`.
- [x] 3.2 In WhatsApp response delivery, branch inline on `is_reaction_response(...)`.
- [x] 3.3 Send reaction responses through `PlatformBotSDK.set_reaction(...)`.
- [x] 3.4 Store successful reaction responses as synthetic bot messages with ID `reaction:{incoming_message_id}`.
- [x] 3.5 Store synthetic reaction text as `<reaction>{emoji}</reaction>`.
- [x] 3.6 Preserve normal responder completion logging and response accounting.
- [x] 3.7 Wrap platform reaction sending with `silent(...)` so reaction API failures do not trigger error replies.

## 4. Tests and Verification

- [x] 4.1 Update existing integration tests for allowed reactions and `is_reaction_response(...)`.
- [x] 4.2 Update existing Telegram responder tests for reaction success and failure behavior.
- [x] 4.3 Update existing WhatsApp responder tests for reaction success and failure behavior.
- [x] 4.4 Run `pipenv run ruff check --fix`.
- [x] 4.5 Run `pipenv run python tools/check_spacing.py --fix`.
- [x] 4.6 Run all tests with `pipenv run pytest -v`.
