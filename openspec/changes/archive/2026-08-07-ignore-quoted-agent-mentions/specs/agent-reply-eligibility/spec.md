## Purpose

Defines when message content makes The Agent eligible to reply in a chat, while keeping historical quoted context separate from newly authored mentions.

## ADDED Requirements

### Requirement: Quoted mentions do not address the agent
The system SHALL consider an agent mention actionable only when it occurs in newly authored, non-quoted text. A mention appearing exclusively on quoted lines SHALL NOT make The Agent eligible to reply.

#### Scenario: Reply contains only a historical mention
- **WHEN** a user sends an untagged group-chat message whose quoted context contains the agent handle and random reply chance is 0%
- **THEN** The Agent does not reply

#### Scenario: New text directly mentions the agent alongside a quote
- **WHEN** a group-chat message contains quoted context and the newly authored text directly mentions the agent
- **THEN** The Agent is eligible to reply regardless of random reply chance

### Requirement: Burst mention carry-over excludes quoted context
When coordinating a debounced burst from one user, the system SHALL carry forward only unanswered agent mentions found in non-quoted text.

#### Scenario: Earlier burst message contains a quoted-only mention
- **WHEN** an earlier message in the same user's burst contains the agent handle only in quoted context and the burst winner is untagged
- **THEN** the quote does not make the burst winner eligible to reply

#### Scenario: Earlier burst message directly mentions the agent
- **WHEN** an earlier message in the same user's burst directly mentions the agent in non-quoted text and no agent response follows it
- **THEN** the untagged burst winner remains eligible to reply

### Requirement: Non-mention reply conditions remain unchanged
The system SHALL continue to use private-chat status and configured random reply chance independently of mention detection.

#### Scenario: Private chat with a quoted-only mention
- **WHEN** a user sends a message in a private chat
- **THEN** The Agent remains eligible to reply even if the only agent mention is quoted

#### Scenario: Group chat selected by random reply behavior
- **WHEN** an untagged group-chat message is selected by the configured random reply behavior
- **THEN** The Agent remains eligible to reply
