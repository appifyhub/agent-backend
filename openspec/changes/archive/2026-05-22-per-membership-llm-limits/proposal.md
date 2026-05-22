## Why

LLM limits (output tokens, context history depth, tool-call iterations) are hardcoded globally — every user in every chat gets identical constraints. This prevents per-user cost control and removes operator flexibility. Additionally, the message/attachment fetching logic is duplicated across responders (Telegram, WhatsApp) rather than owned by the ChatAgent that consumes it, violating single responsibility and creating a maintenance burden.

## What Changes

- Add `max_output_tokens`, `max_chat_history_depth`, and `max_iterations` columns to `ChatMembershipDB`, with defaults matching current hardcoded values (2000, 30, 20)
- Replace the absolute `max_output_tokens` values in `ToolType` with multipliers applied on top of the membership's base token limit
- Move message and attachment fetching from responders into `ChatAgent`, so the agent owns its own context window and trims it according to the membership's `max_chat_history_depth`
- Replace `config.max_chatbot_iterations` usage in `ChatAgent.execute()` with the membership's `max_iterations`
- Expose the new fields through the existing settings API (`UserChatConfigPayload`/`UserChatConfigResponse`)
- Data migration to set defaults for all existing chat memberships

## Capabilities

### New Capabilities
- `membership-llm-limits`: Per-user-per-chat LLM limit configuration (output tokens, history depth, iterations)
- `agent-context-ownership`: ChatAgent self-fetches messages and attachments instead of receiving them from responders

### Modified Capabilities

## Impact

- **DB model**: `chat_memberships` table gains 3 integer columns
- **Migration**: New Alembic migration with data backfill for existing rows
- **API**: `UserChatConfigPayload` and `UserChatConfigResponse` gain 3 new fields
- **ChatAgent**: Constructor signature changes (drops `messages` and `attachment_ids`, fetches internally)
- **Responders**: Telegram and WhatsApp responders shed ~15 lines each of message-fetching logic
- **ToolType**: `max_output_tokens` property becomes a float multiplier
- **langchain_creator**: Reads base tokens from a new source (membership via configured tool or direct param)
