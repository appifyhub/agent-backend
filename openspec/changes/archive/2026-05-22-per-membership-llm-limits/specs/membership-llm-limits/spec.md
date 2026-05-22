## ADDED Requirements

### Requirement: Chat membership stores LLM limits
The `ChatMembershipDB` model SHALL include `max_output_tokens` (integer, default 2000), `max_chat_history_depth` (integer, default 30), and `max_iterations` (integer, default 20) columns.

#### Scenario: New membership created with defaults
- **WHEN** a new chat membership is created without specifying LLM limits
- **THEN** the membership SHALL have `max_output_tokens=2000`, `max_chat_history_depth=30`, `max_iterations=20`

#### Scenario: Existing memberships receive defaults via migration
- **WHEN** the data migration runs on an existing database
- **THEN** all existing chat membership rows SHALL have `max_output_tokens=2000`, `max_chat_history_depth=30`, `max_iterations=20`

### Requirement: ToolType provides output token multiplier
The `ToolType` enum SHALL expose an `output_token_multiplier` float property instead of absolute `max_output_tokens`. The multiplier values SHALL be: chat=1.0, reasoning=2.0, copywriting=2.0, vision=1.5, search=2.0.

#### Scenario: Resolved token count for chat purpose
- **WHEN** a membership has `max_output_tokens=2000` and the purpose is `ToolType.chat`
- **THEN** the resolved output token limit SHALL be `int(2000 * 1.0) = 2000`

#### Scenario: Resolved token count for reasoning purpose
- **WHEN** a membership has `max_output_tokens=2000` and the purpose is `ToolType.reasoning`
- **THEN** the resolved output token limit SHALL be `int(2000 * 2.0) = 4000`

#### Scenario: Custom base with multiplier
- **WHEN** a membership has `max_output_tokens=3000` and the purpose is `ToolType.vision`
- **THEN** the resolved output token limit SHALL be `int(3000 * 1.5) = 4500`

### Requirement: ChatAgent uses membership iteration limit
The `ChatAgent` tool-call loop SHALL use `membership.max_iterations` instead of `config.max_chatbot_iterations`. When membership is unavailable, it SHALL fall back to `config.max_chatbot_iterations`.

#### Scenario: Membership iteration limit enforced
- **WHEN** a membership has `max_iterations=10` and the agent reaches 11 iterations
- **THEN** the agent SHALL raise an `InternalError` and stop processing

#### Scenario: Fallback to global config when no membership
- **WHEN** membership is not available and the agent reaches `config.max_chatbot_iterations + 1` iterations
- **THEN** the agent SHALL raise an `InternalError` and stop processing

### Requirement: Settings API exposes LLM limits
The `UserChatConfigPayload` and `UserChatConfigResponse` models SHALL include `max_output_tokens`, `max_chat_history_depth`, and `max_iterations` fields.

#### Scenario: Reading settings returns LLM limits
- **WHEN** a user requests their chat settings
- **THEN** the response SHALL include `max_output_tokens`, `max_chat_history_depth`, and `max_iterations` from their membership

#### Scenario: Updating LLM limits via settings API
- **WHEN** a user submits updated settings with `max_output_tokens=3000`
- **THEN** the membership SHALL be updated and subsequent LLM calls SHALL use the new base value
