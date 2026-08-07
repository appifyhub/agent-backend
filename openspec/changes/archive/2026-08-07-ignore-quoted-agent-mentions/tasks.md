## 1. Regression Coverage

- [x] 1.1 Add focused cases to `test/features/chat/test_chat_agent.py` proving that single-level and nested quoted-only mentions do not trigger a reply at 0% random chance.
- [x] 1.2 Add cases proving that an unquoted direct mention remains actionable when the same message also contains a quote.
- [x] 1.3 Add burst-history cases proving that quoted-only mentions are not carried forward while genuine unquoted unanswered mentions still are.

## 2. Reply Eligibility

- [x] 2.1 Add a minimal `ChatAgent` helper that derives non-quoted text by excluding lines with a `>>` quote prefix.
- [x] 2.2 Use non-quoted text consistently for direct addressability, unanswered burst mention detection, and the associated known-command check without altering stored or LLM-visible message content.

## 3. Verification

- [x] 3.1 Run the focused offline `ChatAgent` test module and confirm all direct, quoted, nested, burst, private-chat, and random-reply scenarios pass.
- [x] 3.2 Run Ruff and the spacing checker on the changed Python files and confirm they pass.
- [x] 3.3 Run strict OpenSpec validation for `ignore-quoted-agent-mentions` and confirm the change remains valid.
