## Why

When the chat agent encounters an error (policy not accepted, model misconfigured, LLM failure, etc.), it dumps the full error text — including technical details and error codes — directly into the originating chat. This is noisy in group chats, exposes internals unnecessarily, and tells the user to "Open /settings" as plain text rather than providing a clickable link. The `/settings` command and LLM tools already know how to send a proper settings button to the user's private chat — error handling should do the same.

## What Changes

- Error responses in the originating chat are reduced to just the error emoji (e.g. 🤯) when a private chat is available for the detailed message.
- Full error details (message, code) plus a clickable settings link are sent to the user's private chat instead.
- When no private chat is available, fall back to the current behavior but with updated copy: "Check settings" instead of "Open /settings".
- Private-chat delivery failures are logged as warnings and silently swallowed — never propagated up.

## Capabilities

### New Capabilities
- `error-routing`: Route chat agent error details to the user's private chat with a settings link, keeping the originating chat clean.

### Modified Capabilities
