## 1. Fallback copy update

- [x] 1.1 Change "Open /settings" to "Check settings" in `prompt_resolvers.simple_chat_error`

## 2. Error routing helper

- [x] 2.1 Add `__route_error_to_user(self, error_text, emoji) -> AIMessage` method to `ChatAgent` that resolves the private chat, sends error detail + settings link there, and returns emoji-only `AIMessage` (or falls back to `simple_chat_error` when no private chat)
- [x] 2.2 Add required imports to `chat_agent.py` (`resolve_private_chat_id` and any others needed)

## 3. Wire error sites

- [x] 3.1 Replace `simple_chat_error` call at the `require_user_is_chat_ready` error site (line ~160) with `__route_error_to_user`
- [x] 3.2 Replace `simple_chat_error` call at the "no configured tool" error site (line ~167) with `__route_error_to_user`
- [x] 3.3 Replace `simple_chat_error` calls at the LLM processing error sites (lines ~222, ~227) with `__route_error_to_user`
- [x] 3.4 Replace `simple_chat_error` calls in `process_commands` error sites (lines ~237, ~245, ~250) with `__route_error_to_user`

## 4. Tests

- [x] 4.1 Update existing `ChatAgent` tests for the new error routing behavior (emoji-only reply when private chat available, full text fallback otherwise)
- [x] 4.2 Test that private chat delivery failures are swallowed (warning logged, emoji still returned)
- [x] 4.3 Test the "Check settings" copy change in `simple_chat_error`

## 5. Lint and verify

- [x] 5.1 Run ruff and check_spacing on changed files
- [x] 5.2 Run full test suite to confirm no regressions
