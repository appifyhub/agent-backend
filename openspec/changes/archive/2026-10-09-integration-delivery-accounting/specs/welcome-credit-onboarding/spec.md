## Purpose

Fund a new user's first pre-EULA messaging responses while preserving policy and waitlist authorization and avoiding duplicate welcome grants.

## ADDED Requirements

### Requirement: Identical welcome grants at account creation
The first Telegram or WhatsApp message that creates an account SHALL grant the configured welcome-credit amount exactly once through existing transfer bookkeeping. Both platform branches SHALL use the same save-without-commit, grant-without-commit, then single-commit sequence. Creation and the grant SHALL commit atomically. Creation SHALL NOT send a welcome-credit notification, and later updates to the same account SHALL NOT grant again.

#### Scenario: New Telegram account
- **WHEN** a Telegram message creates a new account
- **THEN** the account balance includes the configured welcome grant
- **AND** one corresponding welcome transfer record exists
- **AND** no grant notification is sent during creation

#### Scenario: New WhatsApp account
- **WHEN** a WhatsApp message creates a new account
- **THEN** the account balance includes the configured welcome grant before its first outbound delivery preflight

#### Scenario: Existing account message
- **WHEN** a later message updates an existing Telegram or WhatsApp account
- **THEN** no additional welcome credits or transfer records are created

#### Scenario: Atomic creation failure
- **WHEN** account creation or welcome-grant bookkeeping fails
- **THEN** neither the new account nor a partial welcome grant is committed

### Requirement: EULA acceptance is notification-only
The account's false-to-true EULA transition SHALL persist without minting or transferring credits. After that transition commits, the system SHALL notify the user of the welcome amount already granted only when the configured welcome amount is greater than zero. The notification decision SHALL NOT compare the configured amount with the user's current balance.

#### Scenario: First acceptance with a positive welcome amount
- **WHEN** a newly created account accepts the EULA and the configured welcome amount is positive
- **THEN** its balance and welcome transfer records remain unchanged
- **AND** it receives one welcome-credit notification after the settings change commits

#### Scenario: Credits were spent before acceptance
- **WHEN** delivery or another valid operation has reduced the user's balance before EULA acceptance
- **THEN** the positive welcome-grant notification is still sent after acceptance commits

#### Scenario: Zero configured welcome amount
- **WHEN** the account accepts the EULA and the configured welcome amount is zero
- **THEN** no welcome-credit notification is sent

### Requirement: Authorization remains independent
Moving the grant SHALL NOT bypass existing EULA or waitlist model-authorization rules. There SHALL be no age-based grant eligibility window or grant backfill for existing accounts. The retained-history command recovery policy applies only when existing credits cannot fund delivery and SHALL NOT grant model access.

#### Scenario: Pre-EULA settings command
- **WHEN** a new WhatsApp account requests settings before accepting the EULA
- **THEN** its existing welcome grant may fund ordinary delivery
- **AND** model access remains blocked by the existing policy gate

#### Scenario: Waitlisted account creation
- **WHEN** a new account is waitlisted
- **THEN** it receives the one-time welcome grant
- **AND** existing waitlist restrictions remain in force
