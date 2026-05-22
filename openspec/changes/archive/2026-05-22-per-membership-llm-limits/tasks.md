## 1. Domain and DB Model

- [x] 1.1 Add `max_output_tokens` (int, default 2000), `max_chat_history_depth` (int, default 30), `max_iterations` (int, default 20) to `ChatMembership` dataclass
- [x] 1.2 Add matching columns to `ChatMembershipDB` with `server_default` values
- [x] 1.3 Update `ChatMembershipMapper` to map the new fields between DB and domain models
- [x] 1.4 Update `docs/open-api-docs.yaml`: add `max_output_tokens`, `max_chat_history_depth`, `max_iterations` to `UserChatConfigPayload` and `UserChatConfigResponse` schemas
- [x] 1.5 Create `CHANGELOG.md` documenting the per-membership LLM limits change for frontend reference
- [x] 1.6 Ask user to generate Alembic migration, then verify it includes data backfill for existing rows

## 2. ToolType Multiplier

- [x] 2.1 Replace `ToolType.max_output_tokens` property with `output_token_multiplier` (float) — chat=1.0, reasoning=2.0, copywriting=2.0, vision=1.5, search=2.0
- [x] 2.2 Update `langchain_creator.create()` to accept a resolved `max_output_tokens` int instead of reading from `purpose.max_output_tokens`
- [x] 2.3 Add `max_output_tokens_override` field to `ConfiguredTool` (optional int, default None) — `langchain_creator` uses it when present

## 3. ChatAgent Context Ownership

- [x] 3.1 Move message fetching (CRUD + ChatMessage mapping + langchain mapping) from responders into `ChatAgent.__init__`, using `membership.max_chat_history_depth` with fallback to `config.chat_history_depth`
- [x] 3.2 Move attachment fetching into `ChatAgent.__init__` alongside message fetching
- [x] 3.3 Simplify `ChatAgent` constructor: drop `messages` and `attachment_ids` parameters
- [x] 3.4 Update `DI.chat_agent()` factory to match new constructor signature
- [x] 3.5 Simplify `TelegramUpdateResponder` — remove message/attachment fetching, pass only `raw_last_message`, `last_message_id`, `configured_tool`
- [x] 3.6 Simplify `WhatsAppUpdateResponder` — same changes as Telegram

## 4. Membership Limits in ChatAgent

- [x] 4.1 Replace `config.max_chatbot_iterations` with `membership.max_iterations` (with config fallback) in `ChatAgent.execute()`
- [x] 4.2 Compute resolved output token limit (`membership.max_output_tokens * purpose.output_token_multiplier`) and set it on `ConfiguredTool.max_output_tokens_override` before creating the model

## 5. API Layer

- [x] 5.1 Add `max_output_tokens`, `max_chat_history_depth`, `max_iterations` to `UserChatConfigPayload` and `UserChatConfigResponse`
- [x] 5.2 Update `chat_settings_mapper.domain_to_api()` to include the new fields
- [x] 5.3 Update `settings_controller.__apply_user_chat_config_changes()` to persist the new fields

## 6. Service Layer Bookkeeping

- [x] 6.1 Update all `ChatMembership(...)` construction sites in `ChatMembershipService` to include the new fields (sync, refresh_chat_memberships)
- [x] 6.2 Update `ChatMembershipRepo.save()` to persist the new fields
- [x] 6.3 Update `SpendingService` if it reads `max_output_tokens` from `ToolType` — it should use the resolved value

## 7. Verification

- [x] 7.1 Update existing tests for ChatAgent, responders, and settings to reflect new signatures and behavior
- [x] 7.2 Run linting (`pipenv run pre-commit run --all-files --show-diff-on-failure`)
- [x] 7.3 Run full test suite
