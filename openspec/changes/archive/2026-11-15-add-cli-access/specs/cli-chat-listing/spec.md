# Spec Delta

## Purpose

Let a command-line user discover which chats they can send notifications to, so they can pick a default chat without opening the web settings.

## ADDED Requirements

### Requirement: List the chats the owner administers
An authenticated CLI client SHALL be able to list the chats its owner owns or administers, each as chat id (32-character hex), platform, title (possibly null), and a private flag. Private chats SHALL come first, then chats SHALL be ordered by platform, case-insensitive title, and id. A chat where the owner is only a member SHALL NOT be listed.

#### Scenario: Private and group chats
- **WHEN** the owner has a private Telegram chat and administers a Telegram group
- **THEN** the response is 200 with both chats, the private chat first, each with `chat_id`, `platform`, `title`, and `is_private`

#### Scenario: Member-only chats are omitted
- **WHEN** the owner is a plain member of a group
- **THEN** that group is not in the list

#### Scenario: Other users' private chats are omitted
- **WHEN** other users have private chats with the agent
- **THEN** none of them appears in the owner's list

#### Scenario: No chats
- **WHEN** the owner owns or administers no chat
- **THEN** the response is 200 with an empty list

#### Scenario: Untitled chat
- **WHEN** a listed chat has no title
- **THEN** its `title` is null

#### Scenario: Minimal fields
- **WHEN** chats are listed
- **THEN** each entry contains only `chat_id`, `platform`, `title`, and `is_private`, with the full title unabridged

### Requirement: Listing tolerates platform lookup failures
When the platform cannot confirm the owner's rights in one chat, the listing SHALL omit that chat and still return every other chat the owner administers.

#### Scenario: One group cannot be checked
- **WHEN** the platform lookup for one group fails and the owner administers another group
- **THEN** the response is 200 with the owner's other chats and without the failed group

### Requirement: Listing requires an active CLI token
The listing route SHALL accept only active CLI tokens under the token-scope rules.

#### Scenario: Revoked token
- **WHEN** a revoked CLI token requests the listing
- **THEN** the response is 401 with error code CLI_ACCESS_REVOKED

#### Scenario: Web token
- **WHEN** a web session token requests the listing
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN
