## Context

See proposal.md for motivation.

Currently, all error paths in `ChatAgent.execute()` and `ChatAgent.process_commands()` call `prompt_resolvers.simple_chat_error(...)` which formats the full error text with an "Open /settings" footer and returns it as an `AIMessage` to the originating chat. The plumbing to send a settings button link to the user's private chat already exists — used by `configure_settings` LLM tool and the `/settings` command in `CommandProcessor`. This change wires the error paths to reuse that plumbing.

Key existing pieces:
- `resolve_private_chat_id(user, chat_type)` → returns `str | None`
- `di.settings_controller.create_settings_link()` → returns `SettingsLinkResponse` (can raise)
- `di.platform_bot_sdk().send_button_link(chat_id, url)` → sends a clickable button
- `di.platform_bot_sdk().send_text_message(chat_id, text)` → sends plain text

## Goals / Non-Goals

**Goals:**
- Route error details + settings link to the user's private chat when available
- Keep the originating chat clean (emoji-only reply on error)
- Gracefully degrade to current behavior (inline text) when no private chat exists
- Update fallback copy from "Open /settings" to "Check settings"

**Non-Goals:**
- Changing responder-level error handling (`__notify_of_errors` in telegram/whatsapp update responders) — those stay as-is
- Changing how the `/settings` command or LLM tools send settings links
- Adding new error types or changing error codes

## Decisions

### 1. New private helper method on `ChatAgent`

Add a `__route_error_to_user(self, error_text: str, emoji: str) -> AIMessage` method that encapsulates the routing logic:

1. Try to resolve the user's private chat ID via `resolve_private_chat_id`
2. If available: send the error text + settings button link to the private chat, return `AIMessage(emoji)` for the originating chat
3. If not available: return `AIMessage(simple_chat_error(error_text, emoji))` (current behavior with updated copy)
4. If the private chat send fails: log warning, return `AIMessage(emoji)` anyway — don't propagate

**Rationale:** Centralizes the branching logic in one place. All 6 error sites in `ChatAgent` call this instead of directly calling `simple_chat_error`.

**Alternative considered:** Putting the routing logic in `simple_chat_error` itself. Rejected because `simple_chat_error` is a pure text formatter used by responders too — it shouldn't acquire DI dependencies or side effects.

### 2. Error detail format in private chat

Send two messages to the private chat:
1. A text message with the error detail: `"{emoji}\n\n{error_text}"`
2. A button link to settings via `send_button_link`

This matches how the `/settings` command already sends its response — a message followed by a button.

### 3. Settings link creation failure handling

`create_settings_link()` can raise (e.g., no external ID). If it does, the error text still gets sent to the private chat as a plain text message, but no button link follows. The failure is logged as a warning.

### 4. Fallback copy change

`simple_chat_error` updates its footer from `"Open /settings"` to `"Check settings"`. This is a one-line change in `prompt_resolvers.py`.

## Risks / Trade-offs

- **Double messaging in private chats:** When the originating chat IS the private chat, the user sees the emoji reply followed by the error detail + settings link in the same conversation. This is acceptable — it's the same chat, so the context is clear.
- **Settings link irrelevance:** Some errors (like max iterations exceeded) aren't fixable via settings. The settings link is still sent because the user's configuration (model choice, iteration limits) is genuinely adjustable there. This is a reasonable default.
- **Swallowed failures:** If private chat delivery fails silently, the user only sees the emoji in the originating chat with no explanation. This is the intended behavior — a clean chat is preferred over noisy fallback errors.
