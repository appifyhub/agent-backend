## Context

Telegram and WhatsApp both support reacting to an existing message. The current chat responder flow always treats a non-empty `AIMessage` as text to map, store, and send, which makes a one-emoji acknowledgement appear as a new chat message instead of a native reaction.

The response delivery logic lives in the platform responders, while chat prompt construction lives in the prompt resolver/library. Reaction support already exists behind `PlatformBotSDK.set_reaction(...)`.

## Goals / Non-Goals

**Goals:**

- Allow the chat model to intentionally produce exactly one allowed reaction emoji for lightweight acknowledgements.
- Keep detection simple with `is_reaction_response(text, chat_type)`.
- Preserve future chat context by storing a synthetic bot-authored message using `<reaction>{emoji}</reaction>`.
- Keep Telegram and WhatsApp response flow logging and read handling aligned with normal text responses.
- Keep unsupported chat types, such as GitHub, from using reaction-only responses for now.

**Non-Goals:**

- No reaction support for GitHub.
- No fuzzy extraction from longer model responses.
- No new database columns or migrations.
- No long-lived baseline spec retention requirement for this feature work.

## Decisions

- Use platform allow lists from `integration_config.py`.
  - Rationale: these lists already define what each platform can receive.
  - Alternative considered: hard-code a smaller prompt-only list. Rejected because it would drift from platform support.

- Use `is_reaction_response(text, chat_type)` as an exact trimmed-string membership check.
  - Rationale: this keeps the branch explicit and avoids parsing or extracting a reaction from mixed text.
  - Alternative considered: extract the first allowed emoji from the model response. Rejected because it could turn ambiguous text into unintended reactions.

- Keep reaction handling inline in the Telegram and WhatsApp responder send/store block.
  - Rationale: the existing block calculates `sent_messages`, resolves the agent, logs completion, and marks WhatsApp messages as read. Reaction handling should preserve that flow.
  - Alternative considered: a separate helper that returns early. Rejected because it bypasses shared response accounting and logging.

- Store synthetic reaction history as `reaction:{incoming_message_id}` with text `<reaction>{emoji}</reaction>`.
  - Rationale: the deterministic message ID makes retries idempotent through `chat_message_crud.save(...)`, and the marker is readable by future prompt history.
  - Alternative considered: do not store reactions. Rejected because future replies need to see that the agent resolved the user request.

- Treat platform reaction delivery as best-effort after storing the synthetic history message.
  - Rationale: a platform reaction API failure should not turn a lightweight acknowledgement into a user-visible error response.
  - Alternative considered: let reaction failures flow to the outer responder error handler. Rejected because the durable chat-history signal is already recorded.

## Risks / Trade-offs

- Reaction API failure can leave only the synthetic history marker without a visible platform reaction -> The platform API call is wrapped with `silent(...)` because preserving chat flow is more important than surfacing a failed acknowledgement reaction.
- The model may still send a short text instead of a reaction -> The prompt encourages, but does not force, reaction-only output.
- The synthetic marker is plain text in history -> This is acceptable because history already carries formatted bot text, and the marker is intentionally simple.
