## Purpose

Define how newly created platform profiles receive a one-time, fully fungible welcome credit transfer after timely EULA acceptance.

## ADDED Requirements

### Requirement: Welcome grant configuration
The system SHALL configure the welcome transfer amount and the maximum profile age in whole calendar days at EULA acceptance. The default amount SHALL be 500 credits and the default maximum age SHALL be 7 days.

#### Scenario: Default configuration
- **WHEN** no welcome grant configuration overrides are provided
- **THEN** the system uses a 500-credit transfer amount and a 7-day maximum profile age

#### Scenario: Overridden configuration
- **WHEN** valid welcome grant configuration overrides are provided
- **THEN** the system uses the configured transfer amount and maximum profile age

### Requirement: Policy acceptance precedes other settings
The system SHALL reject settings updates from an unaccepted profile unless the payload confirms policy acceptance with `true`. A payload value of `false` SHALL always be rejected. After policies have been accepted, an omitted or `null` acceptance field SHALL preserve the accepted state while allowing ordinary settings changes.

#### Scenario: Unaccepted profile omits policy acceptance
- **WHEN** a profile that has not accepted policies submits other settings without `are_policies_accepted=true`
- **THEN** the settings update is rejected without persisting any changes

#### Scenario: Accepted profile omits policy acceptance
- **WHEN** a profile that already accepted policies submits an ordinary settings update without the acceptance field
- **THEN** the other settings are saved and policy acceptance remains unchanged

### Requirement: Grant on timely first EULA acceptance
The system SHALL issue one welcome transfer when a profile changes from not having accepted the EULA to having accepted it and the profile age is not greater than the configured maximum age. Eligibility SHALL depend on the profile lifecycle and SHALL NOT depend on its current credit balance, purchase history, or sponsorship status.

#### Scenario: Eligible first acceptance
- **WHEN** a profile first accepts the EULA no later than 7 whole calendar days after its creation under the default configuration
- **THEN** the profile receives 500 credits

#### Scenario: Acceptance at the eligibility boundary
- **WHEN** a profile first accepts the EULA exactly the configured number of whole calendar days after its creation
- **THEN** the profile receives the welcome transfer

#### Scenario: Acceptance after the eligibility window
- **WHEN** a profile first accepts the EULA more than the configured number of whole calendar days after its creation
- **THEN** the EULA acceptance and any permitted activation still succeed without a welcome transfer

#### Scenario: Existing balance does not affect eligibility
- **WHEN** an otherwise eligible profile first accepts the EULA while it already has credits or purchase history
- **THEN** the profile still receives the full configured welcome transfer

#### Scenario: Sponsored recipient
- **WHEN** an otherwise eligible sponsored profile first accepts the EULA
- **THEN** the profile receives the welcome transfer despite ordinary peer-transfer restrictions on sponsored recipients

### Requirement: One transfer per platform profile
The system SHALL issue at most one welcome transfer for each platform profile. A request that observes an already accepted EULA SHALL NOT issue another welcome transfer.

#### Scenario: Repeated acceptance request
- **WHEN** a profile that already accepted the EULA submits settings with EULA acceptance again
- **THEN** the profile receives no additional welcome credits

#### Scenario: Concurrent acceptance requests
- **WHEN** concurrent requests attempt the same profile's first EULA acceptance
- **THEN** exactly one request issues the welcome transfer and the profile receives the configured amount only once

#### Scenario: Profiles later connected
- **WHEN** two independently eligible platform profiles each receive a welcome transfer and are later connected
- **THEN** both balances contribute additively to the merged profile

### Requirement: Ordinary transferable credits
Credits received through the welcome transfer SHALL be indistinguishable from other credits after receipt. They SHALL have no promotional bucket, expiration, spending priority, refund protection, or restrictions based on their welcome origin. Existing user-level restrictions SHALL continue to apply regardless of credit origin.

#### Scenario: Use welcome credits
- **WHEN** a profile receives welcome credits
- **THEN** subsequent spending, transfers, sponsorship eligibility, and profile merging use the same balance behavior as credits from any other source

#### Scenario: Sponsored billing precedence
- **WHEN** a profile with welcome credits is sponsored
- **THEN** the existing sponsorship billing precedence remains in effect and the receiver's balance remains untouched while the sponsorship is active

### Requirement: Transfer provenance
The welcome allocation SHALL appear in credit history as a credit transfer of the configured amount from `THE_AGENT` to the recipient with the note `"Welcome"`. In the same transaction, issuance SHALL first add the amount to `THE_AGENT` without a separate history record and then execute the ordinary transfer, leaving `THE_AGENT` with the same final balance.

#### Scenario: Successful welcome transfer history
- **WHEN** an eligible EULA acceptance commits
- **THEN** credit history contains one transfer from `THE_AGENT` to the profile for the configured amount with the note `"Welcome"`

#### Scenario: System agent balance
- **WHEN** a welcome transfer succeeds
- **THEN** `THE_AGENT` has no net balance change

### Requirement: Atomic acceptance and issuance
The system SHALL commit the EULA transition, waitlist activation changes, temporary `THE_AGENT` balance increase, ordinary transfer balance movement, and transfer-history record in one locked database transaction. Failure of any database operation SHALL leave all of those values unchanged.

#### Scenario: Transfer recording fails
- **WHEN** transfer-history persistence fails during an otherwise eligible EULA acceptance
- **THEN** the EULA state, activation flags, recipient balance, and transfer history are all rolled back, and `THE_AGENT` remains unchanged

#### Scenario: Ineligible acceptance
- **WHEN** a profile accepts the EULA outside the eligibility window
- **THEN** EULA and activation changes commit without changing either balance or creating a welcome transfer record
