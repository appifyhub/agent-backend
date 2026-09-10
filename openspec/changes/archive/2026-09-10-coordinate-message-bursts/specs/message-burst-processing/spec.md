## Purpose

Define how incoming conversational messages are combined into user bursts and processed exactly once across service instances without delaying commands or retaining database resources while waiting.

## ADDED Requirements

### Requirement: Messages form per-author quiet-period bursts
The system SHALL group non-command messages by chat and author. A burst SHALL become eligible for processing only after 1 second has elapsed since the most recently received non-command message for that chat and author.

#### Scenario: Several messages arrive within the quiet period
- **WHEN** multiple non-command messages from one author in one chat arrive with less than 1 second of silence between them
- **THEN** the system treats them as one burst and starts no response processing until 1 second after the last message arrives

#### Scenario: A later message arrives after the quiet period
- **WHEN** a message arrives more than 1 second after the preceding burst became eligible and was claimed
- **THEN** the system treats the later message as part of a new burst

#### Scenario: Different authors send messages concurrently
- **WHEN** messages from different authors arrive in the same group chat
- **THEN** each author's quiet period and burst are tracked independently

### Requirement: Burst claiming is coordinated across instances
The system SHALL use shared database state to ensure that no more than one service instance claims a settled burst for response processing.

#### Scenario: Multiple delayed attempts wake for one burst
- **WHEN** delayed attempts created by several messages or service instances wake for the same chat and author
- **THEN** only the attempt matching the current settled message count claims response processing

#### Scenario: An obsolete attempt wakes
- **WHEN** a delayed attempt wakes after a newer message has extended the burst deadline
- **THEN** the obsolete attempt performs no response processing

### Requirement: Waiting does not retain database resources
The system SHALL commit and release the database session and transaction used to record a message before waiting for the quiet period. The delayed attempt SHALL acquire a fresh database session only after its asynchronous wait completes.

#### Scenario: A burst is waiting for additional messages
- **WHEN** a delayed attempt is suspended during the 1 second quiet period
- **THEN** that attempt holds no database transaction or checked-out database connection

### Requirement: Commands bypass burst processing
The system SHALL process each recognized command immediately without waiting for the burst quiet period. A command SHALL NOT extend, replace, or be claimed as part of a conversational burst.

#### Scenario: A command arrives without other messages
- **WHEN** the system receives a recognized command
- **THEN** command processing begins without a burst delay

#### Scenario: A command arrives during a conversational burst
- **WHEN** a recognized command arrives while non-command messages from the same author are waiting for their quiet period
- **THEN** the command is processed immediately and the existing conversational burst retains its own deadline

### Requirement: Group-chat reply eligibility is evaluated per burst
For a group chat, the system SHALL preserve the existing reply-decision behavior while evaluating it once for each settled author burst. If any message in the burst explicitly addresses the bot, the burst SHALL be treated as explicitly addressed even when the final burst message does not repeat the tag.

#### Scenario: A tagged message is followed by untagged fragments
- **WHEN** an author sends a tagged message followed within the same burst by untagged attachments or text
- **THEN** the system evaluates and processes one explicitly addressed burst containing all of those messages

#### Scenario: Two authors tag the bot
- **WHEN** two authors independently send tagged bursts in one group chat
- **THEN** each author's settled burst remains eligible for its own reply

#### Scenario: A burst does not tag the bot
- **WHEN** no message in a settled group-chat burst explicitly addresses the bot
- **THEN** the existing non-mention reply-decision behavior is applied once to that burst

### Requirement: Private-chat messages are evaluated as one addressed burst
The system SHALL treat every settled private-chat burst as explicitly addressed and SHALL produce at most one response for that burst.

#### Scenario: Photos and a prompt arrive as separate deliveries
- **WHEN** a private-chat user sends multiple photos and prompt text within one burst
- **THEN** the system invokes conversational processing once with all burst messages available as context

### Requirement: Processing uses a stable burst cutoff
The system SHALL evaluate a burst using chat history through the burst's final logical message and SHALL exclude messages logically after that cutoff. Message ordering SHALL be deterministic when platform timestamps are equal or deliveries arrive out of order.

#### Scenario: Another message arrives after a burst is claimed
- **WHEN** a burst has been claimed and a later message is received
- **THEN** the claimed processing uses its original cutoff and the later message is assigned to subsequent processing

#### Scenario: Messages have equal platform timestamps
- **WHEN** two stored messages have equal platform timestamps
- **THEN** the system applies a stable database-backed ordering to determine the burst cutoff and history order

