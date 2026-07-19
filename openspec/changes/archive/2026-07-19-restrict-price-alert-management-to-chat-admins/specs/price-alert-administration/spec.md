## ADDED Requirements

### Requirement: Price-alert mutations require current chat-administrator access
The system SHALL allow only a current administrator of the target chat to create, reconfigure, or remove that chat's price alerts. The system SHALL use the existing chat-administration rules, including treating the owner of a supported private chat as its administrator.

#### Scenario: Administrator creates a new price alert
- **WHEN** a current chat administrator requests a price alert for a currency pair that does not yet exist in the chat
- **THEN** the system creates the alert for that chat
- **THEN** the invoking administrator becomes the alert owner

#### Scenario: Administrator reconfigures an existing price alert
- **WHEN** a current chat administrator requests a price alert for a currency pair that already exists in the chat
- **THEN** the system replaces the existing alert state using the requested threshold and current rate
- **THEN** the invoking administrator becomes the alert owner

#### Scenario: Administrator removes a price alert
- **WHEN** a current chat administrator requests removal of a price alert in the chat
- **THEN** the system removes the matching alert if it exists

#### Scenario: Ordinary member attempts to create or reconfigure a price alert
- **WHEN** a chat member who is not a current administrator requests creation or reconfiguration of a price alert
- **THEN** the system rejects the request with the existing not-chat-administrator authorization error
- **THEN** the system does not fetch the current exchange rate or persist alert state

#### Scenario: Ordinary member attempts to remove a price alert
- **WHEN** a chat member who is not a current administrator requests removal of a price alert
- **THEN** the system rejects the request with the existing not-chat-administrator authorization error
- **THEN** the system does not delete alert state

#### Scenario: Private-chat owner manages a price alert
- **WHEN** the owner of a supported private chat requests creation, reconfiguration, or removal of a price alert
- **THEN** the system authorizes the operation using the existing private-chat ownership rule

#### Scenario: Previously authorized user has lost administrator access
- **WHEN** a user whose stored membership was previously administrative requests a price-alert mutation after losing platform administrator access
- **THEN** the system refreshes the user's chat authorization
- **THEN** the system rejects the mutation without changing alert state

### Requirement: Chat members retain price-alert visibility
The system SHALL continue allowing chat members to list the active price alerts for their current chat without requiring administrator access.

#### Scenario: Ordinary member lists active price alerts
- **WHEN** a chat member who is not an administrator requests the active price alerts for the current chat
- **THEN** the system returns the chat's active price alerts

### Requirement: Administrative controls do not alter background alert processing
The system SHALL apply chat-administrator authorization only to interactive price-alert management and SHALL preserve existing background alert evaluation and maintenance behavior.

#### Scenario: Scheduled alert evaluation processes administrator-created alerts
- **WHEN** scheduled alert evaluation checks persisted price alerts
- **THEN** the system evaluates, refreshes, and delivers triggered alerts without requiring an interactive administrator context

#### Scenario: Stale alert cleanup runs
- **WHEN** scheduled cleanup removes stale price alerts
- **THEN** the system preserves the existing stale-alert deletion behavior without requiring chat-administrator authorization
