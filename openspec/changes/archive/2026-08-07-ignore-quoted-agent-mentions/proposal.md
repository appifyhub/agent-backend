## Why

In group chats with random reply chance set to 0%, The Agent can treat an `@` mention copied into quoted or replied-to context as a fresh address and reply unexpectedly. Reply eligibility must distinguish text authored in the triggering conversation turn from historical text included only for context.

## What Changes

- Ignore agent mentions that occur only inside formatted quote lines when deciding whether a group-chat message requires a reply.
- Apply the same rule while carrying an unanswered mention across a debounced message burst.
- Preserve replies for direct mentions in newly authored text, including messages that also contain quoted context.
- Preserve existing private-chat and random-reply behavior.

## Capabilities

### New Capabilities

- `agent-reply-eligibility`: Defines which direct and burst-carried mentions make The Agent eligible to reply, excluding mentions present only in quoted context.

### Modified Capabilities

None.

## Impact

- Affects group-chat reply decisions in `src/features/chat/chat_agent.py`.
- Uses the existing `>>` quote representation produced by Telegram and WhatsApp inbound formatting.
- Requires focused `ChatAgent` regression coverage; no API, schema, migration, or dependency changes are expected.
