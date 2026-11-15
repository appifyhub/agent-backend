# Spec Delta

## Purpose

Let a user attach a command-line client to their existing profile by redeeming their connect key for a scoped, expiring access token, with predictable lifetime rules, single-use keys, and an alert whenever a new device connects.

## ADDED Requirements

### Requirement: Connect key redemption issues a CLI token
The system SHALL let an unauthenticated client redeem a valid connect key together with a device id, hostname, and operating system, and SHALL respond with a signed bearer token, its UTC expiry, the owner's user id, a display name, and the owner's credit balance after any charge made while connecting. The token SHALL act only as the key's owner. Redemption SHALL NOT create or merge profiles; its only change to the profile is rotating the key.

#### Scenario: Successful connect
- **WHEN** a client submits a valid connect key, a device id, a valid hostname, and an operating system
- **THEN** the response is 200 with a token, an RFC 3339 UTC `expires_at`, the owner's user id as 32-character hex, a non-empty display name, and the owner's `credit_balance`

#### Scenario: Token claims
- **WHEN** a token is issued
- **THEN** it carries the owner's user id as subject, scope `cli`, the owner's current revocation generation, the device id, hostname, operating system, issuer, issued-at, expiry, and application version
- **AND** its expiry matches the returned `expires_at` to within one second

#### Scenario: Key formatting is forgiven
- **WHEN** the connect key is submitted in lowercase or with surrounding whitespace
- **THEN** it is accepted as if trimmed and uppercased

#### Scenario: Display name fallback
- **WHEN** the owner has no full name
- **THEN** the display name is the owner's Telegram username, otherwise their WhatsApp phone number, otherwise their user id

#### Scenario: Several devices
- **WHEN** the same owner connects two devices, the second with the rotated key
- **THEN** both tokens are valid at the same time

#### Scenario: Balance without a charge
- **WHEN** no alert is sent during the connect
- **THEN** `credit_balance` is the owner's current balance, unchanged by the connect

### Requirement: Connect is not gated by onboarding state
The system SHALL NOT check the key holder's waitlist or policy-acceptance state when redeeming a connect key. Connect keys are only shown to onboarded users in the web app, so redemption needs no further gate.

#### Scenario: Any key holder
- **WHEN** the holder of a valid key is on the waitlist or has not accepted the policies
- **THEN** the connect succeeds exactly as for any other owner

### Requirement: Unknown or used connect keys are rejected
The system SHALL reject a connect key that matches no user with HTTP 404 and error code CONNECT_KEY_NOT_FOUND. It SHALL NOT distinguish a never-issued key from a rotated one, SHALL NOT echo the submitted key, and SHALL leave all state unchanged.

#### Scenario: Unknown key
- **WHEN** a client submits a key that no user holds
- **THEN** the response is 404 with error code CONNECT_KEY_NOT_FOUND and no token is issued

#### Scenario: Key used before
- **WHEN** a client submits a key that was already redeemed
- **THEN** the response is 404 with error code CONNECT_KEY_NOT_FOUND

#### Scenario: Simultaneous redemption
- **WHEN** two requests redeem the same valid key at the same time
- **THEN** exactly one receives a token and the other receives 404 CONNECT_KEY_NOT_FOUND

### Requirement: Connect key rotates after a successful connect
The system SHALL replace the owner's connect key with a newly generated one in the same atomic operation that issues the token. If the connect fails for any reason the key SHALL remain unchanged. Rotation SHALL NOT revoke any existing CLI token.

#### Scenario: Rotation on success
- **WHEN** a connect succeeds
- **THEN** the owner's stored key differs from the redeemed key and has the form XXXX-XXXX-XXXX
- **AND** the redeemed key can no longer be used

#### Scenario: No rotation on a rejected connect
- **WHEN** a connect is rejected because of its lifetime or device information
- **THEN** the owner's key is unchanged and still redeems

#### Scenario: Existing tokens survive rotation
- **WHEN** a second device connects with the rotated key
- **THEN** the first device's token continues to work

### Requirement: Lifetime grammar
The client SHALL send the requested lifetime as text and only the server SHALL interpret it. A valid value is a positive integer in ASCII digits, without leading zero, sign, or fraction, immediately followed by exactly one case-sensitive unit: `s`, `m` or `min` (minutes), `h`, `d`, `M` or `mo` (months), `y`. Any other text SHALL be rejected with HTTP 400 and error code INVALID_CLI_TTL.

#### Scenario: Accepted forms
- **WHEN** the lifetime is `90s`, `90m`, `90min`, `12h`, `30d`, `3M`, `3mo`, or `1y`
- **THEN** the token expires after 90 seconds, 90 minutes, 90 minutes, 12 hours, 30 days, 3 calendar months, 3 calendar months, and 1 calendar year respectively

#### Scenario: Minutes and months are different units
- **WHEN** the lifetime is `5m` and, in another request, `5M`
- **THEN** the first expires after 5 minutes and the second after 5 calendar months

#### Scenario: Compound lifetimes are rejected
- **WHEN** the lifetime is `1h30m`
- **THEN** the response is 400 with error code INVALID_CLI_TTL

#### Scenario: Other malformed lifetimes are rejected
- **WHEN** the lifetime is `1.5h`, `0d`, `03d`, `-5m`, `+5m`, `5`, `d`, `5 d`, ` 5d`, `5D`, `5days`, `1e3s`, or an empty or blank string
- **THEN** each is rejected with 400 and error code INVALID_CLI_TTL

#### Scenario: Non-ASCII digits are rejected
- **WHEN** the lifetime is written with non-ASCII digits such as `٣d`
- **THEN** the response is 400 with error code INVALID_CLI_TTL

### Requirement: Calendar-precise months and years
Lifetimes in months and years SHALL be computed on the UTC calendar from the moment of connection, clamping to the last day of the target month when the day does not exist. Lifetimes in seconds, minutes, hours, and days SHALL be exact durations, with a day equal to 24 hours.

#### Scenario: Month-end clamping
- **WHEN** a client connects on 31 January and requests `1mo`
- **THEN** the token expires on the last day of February at the same time of day

#### Scenario: Leap-day anniversary
- **WHEN** a client connects on 29 February and requests `1y`
- **THEN** the token expires on 28 February of the following year at the same time of day

#### Scenario: Months ignore day counts
- **WHEN** a client connects on 14 November and requests `3M`
- **THEN** the token expires on 14 February at the same time of day, whatever the number of days in between

#### Scenario: Days are exact
- **WHEN** a client requests `2d`
- **THEN** the token expires exactly 48 hours after connection

### Requirement: Default and maximum lifetime
When no lifetime is requested the token SHALL expire six calendar months after connection. A lifetime that ends later than two calendar years after connection SHALL be rejected with HTTP 400 and error code CLI_TTL_TOO_LONG. A lifetime of exactly two calendar years SHALL be accepted.

#### Scenario: Omitted lifetime
- **WHEN** the lifetime is absent or null
- **THEN** the token expires six calendar months after connection

#### Scenario: Maximum is accepted
- **WHEN** the lifetime is `2y` or `24mo`
- **THEN** the token is issued and expires two calendar years after connection

#### Scenario: Beyond the maximum
- **WHEN** the lifetime is `3y`, `25mo`, or `800d`
- **THEN** the response is 400 with error code CLI_TTL_TOO_LONG and the key is unchanged

#### Scenario: Cap measured on the calendar with a leap day
- **WHEN** the lifetime is `731d` and the two calendar years after connection contain a leap day
- **THEN** the lifetime is accepted

#### Scenario: Cap measured on the calendar without a leap day
- **WHEN** the lifetime is `731d` and the two calendar years after connection contain no leap day
- **THEN** the response is 400 with error code CLI_TTL_TOO_LONG

#### Scenario: Unrepresentable lifetime
- **WHEN** the lifetime is so large that its expiry cannot be represented, such as `99999999999999999999d`
- **THEN** the response is 400 with error code CLI_TTL_TOO_LONG rather than a server error

### Requirement: Device information is validated
The system SHALL accept any non-blank string as the device id, and SHALL require the hostname to be 1 to 32 characters from letters, digits, `.` and `-`, and the operating system to be 1 to 32 characters from letters, digits, `.`, `_`, `/` and `-`. Violations SHALL be rejected with HTTP 422 and error code INVALID_CLI_DEVICE before any state changes.

#### Scenario: Typical devices
- **WHEN** the hostname is `build-box-01` and the operating system is `darwin`, `linux`, or `windows`
- **THEN** the connect proceeds

#### Scenario: Unsafe hostname
- **WHEN** the hostname contains a space, bracket, at sign, newline, or any other character outside the allowed set
- **THEN** the response is 422 with error code INVALID_CLI_DEVICE and the key is unchanged

#### Scenario: Empty or overlong values
- **WHEN** the hostname or operating system is empty or longer than 32 characters
- **THEN** the response is 422 with error code INVALID_CLI_DEVICE

#### Scenario: Blank device id
- **WHEN** the device id is empty or only whitespace
- **THEN** the response is 422 with error code INVALID_CLI_DEVICE

### Requirement: New-device alert
After a successful connect the system SHALL attempt to tell the owner, in their best private chat, that a new CLI connected (hostname, operating system, UTC expiry formatted `YYYY-MM-DD HH:MM`) and that they can revoke all CLI access from the agent's settings. The alert SHALL be a system announcement written by the announcement service, billed like other announcements, and SHALL NOT change the outcome of the connect.

#### Scenario: Alert delivered
- **WHEN** a connect succeeds for an owner with a Telegram private chat
- **THEN** an announcement based on the hostname, operating system, the expiry as UTC `YYYY-MM-DD HH:MM`, and the instruction to open the agent's settings and revoke all CLI access is sent to that chat

#### Scenario: WhatsApp-only owner inside the window
- **WHEN** the owner has only a WhatsApp private chat and wrote there within the last 24 hours
- **THEN** the alert is sent to that chat

#### Scenario: No chat can receive the alert
- **WHEN** the owner has no private chat, or only a WhatsApp chat outside the 24-hour window
- **THEN** no alert is sent and the connect still succeeds

#### Scenario: Owner cannot fund delivery
- **WHEN** the owner lacks the credits needed for one delivery to that chat
- **THEN** no alert is sent and the connect still succeeds

#### Scenario: Delivery fails
- **WHEN** the platform rejects the alert or the request to it times out
- **THEN** the connect still succeeds, the key is rotated, and the failure is logged without secrets

#### Scenario: Billed like any delivery
- **WHEN** the alert is delivered to a chat whose delivery has a price
- **THEN** the owner is charged that price with a delivery usage record
- **AND** when the price is zero the balance is unchanged

#### Scenario: Balance reflects the alert charge
- **WHEN** the alert is delivered and charged during the connect
- **THEN** the `credit_balance` in the response is the owner's balance after that charge

#### Scenario: Rejected connects send no alert
- **WHEN** a connect is rejected for any reason
- **THEN** no alert is sent

### Requirement: Secrets stay out of logs
The system SHALL NOT write connect keys, issued tokens, or authorization headers to logs or error messages produced while handling CLI requests.

#### Scenario: Successful connect
- **WHEN** a connect succeeds
- **THEN** neither the redeemed key, the new key, nor the token appears in any log output

#### Scenario: Unknown key
- **WHEN** a connect is rejected because the key is unknown
- **THEN** the submitted key appears neither in log output nor in the error message
