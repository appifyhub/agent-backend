## Context

LLM limits are currently scattered across two locations:
- `ToolType.max_output_tokens` — hardcoded per purpose (chat=2000, reasoning=4000, vision=3000, etc.)
- `config.chat_history_depth` (30) and `config.max_chatbot_iterations` (20) — global env vars

Message and attachment fetching is duplicated in both `TelegramUpdateResponder` and `WhatsAppUpdateResponder` with identical logic, then passed into `ChatAgent` which has no control over its own context window.

The `ChatMembershipDB` model already holds per-user-per-chat preferences (`use_about_me`, `use_custom_prompt`). LLM limits are the same kind of concern — per-user-per-chat tuning.

## Goals / Non-Goals

**Goals:**
- Users can configure output token limit, history depth, and max iterations per chat
- ChatAgent owns its context: fetches messages and attachments internally using membership limits
- Responders are simplified — they no longer duplicate message-fetching logic
- Existing behavior is preserved via defaults matching current hardcoded values

**Non-Goals:**
- No system-level hard ceiling on top of membership values (users pay with credits)
- No per-ToolType overrides on membership (one base value + multiplier is sufficient)
- No UI changes beyond exposing the new fields in the existing settings API
- Global config values (`CHAT_HISTORY_DEPTH`, `MAX_CHATBOT_ITERATIONS`) are not removed — they remain as fallbacks when membership is unavailable

## Decisions

### 1. Token limit: base value + ToolType multiplier

The membership stores a single `max_output_tokens` (default 2000, the chat baseline). `ToolType` exposes a `output_token_multiplier` property instead of an absolute value:

| ToolType     | Current absolute | Multiplier |
|--------------|-----------------|------------|
| chat         | 2000            | 1.0        |
| reasoning    | 4000            | 2.0        |
| copywriting  | 4000            | 2.0        |
| vision       | 3000            | 1.5        |
| search       | 4000            | 2.0        |

The resolved token count: `int(membership.max_output_tokens * purpose.output_token_multiplier)`.

**Why multiplier over absolute:** Users think in terms of "how verbose should my bot be" — one knob. The per-purpose scaling is an implementation detail they shouldn't need to know about.

**Alternative considered:** Store separate limits per ToolType on membership. Rejected — it exposes internal architecture to end users and adds 5 columns instead of 1.

### 2. ChatAgent self-fetches messages and attachments

ChatAgent's constructor changes from receiving `messages` and `attachment_ids` to fetching them internally via DI:

```
Before: ChatAgent(messages, raw_last_message, last_message_id, attachment_ids, configured_tool, di)
After:  ChatAgent(raw_last_message, last_message_id, configured_tool, di)
```

The agent uses `membership.max_chat_history_depth` (falling back to `config.chat_history_depth`) for the fetch limit. Attachment fetching moves with it — it's only consumed inside the agent.

**Why this upholds SRP:** The agent is the sole consumer of these messages. Having the responder fetch and pass them in meant two components shared responsibility for assembling the LLM context. Now the agent is self-contained.

**Why this is safe:** Both responders have identical fetch logic (same CRUD calls, same mapping, same ordering). No responder-specific customization exists.

### 3. Membership fields with global config fallbacks

When `ChatAgent` cannot resolve a membership (e.g., first message before membership exists), it falls back to the global config values. The resolution order:

1. `membership.max_output_tokens` / `membership.max_chat_history_depth` / `membership.max_iterations`
2. `config` defaults (existing env vars, unchanged)

This keeps the system functional during the membership sync window.

### 4. Where the resolved token limit is applied

`langchain_creator.create()` currently reads `purpose.max_output_tokens` (from the ToolType enum). The change: `ChatAgent` computes the resolved token limit (`base * multiplier`) and passes it through. Two options:

- **Option A**: Add `max_output_tokens` override to `ConfiguredTool` dataclass
- **Option B**: Pass it as a separate parameter to `chat_langchain_model()`

Option A is cleaner — `ConfiguredTool` already flows through to `langchain_creator` and to `SpendingService`. Adding an optional override keeps the call chain unchanged. `langchain_creator` uses `configured_tool.max_output_tokens_override or purpose.max_output_tokens` (where `purpose.max_output_tokens` now applies the multiplier).

### 5. Data migration

New Alembic migration adds 3 columns with `server_default` values, then backfills existing rows. Since the defaults match current behavior, the migration is backward-compatible with zero behavior change for existing users.

## Risks / Trade-offs

- **Users can set very high limits** → Mitigated by credit system; high limits = high cost = self-regulating. No artificial ceiling needed.
- **Multiplier is invisible to the user** → The user sets "max output tokens" but reasoning responses can be 2x that. Acceptable because the setting label can clarify ("base output tokens") and the multiplier preserves the existing ratios users already experience.
- **ChatAgent constructor change touches DI factory** → The `di.chat_agent()` factory method and both responders must be updated atomically. Low risk since it's a signature change, not a behavioral one.
- **Attachment over-fetch eliminated** → Previously the responder fetched attachments for all messages, then ChatAgent might have trimmed some. Now fetch and trim happen together — minor efficiency gain.
