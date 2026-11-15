# Spec Delta

## Purpose

Keep command-line access tokens strictly separate from web session tokens, and verify every CLI request against the owner's current state, so a CLI token can only do CLI things and stops working the moment it is revoked.

## ADDED Requirements

### Requirement: Web routes reject CLI tokens
Every route that authenticates with a web session token SHALL reject tokens that carry a scope claim, with HTTP 401, so a CLI token can never read or change settings, usage, purchases, sponsorships, connect keys, or attachments. Web tokens without a scope claim SHALL keep working exactly as before.

#### Scenario: CLI token on a settings route
- **WHEN** a valid CLI token is presented to a web settings route
- **THEN** the response is 401

#### Scenario: CLI token on an attachment route
- **WHEN** a valid CLI token is presented to the private attachment route
- **THEN** the response is 401

#### Scenario: CLI token on the web revoke route
- **WHEN** a valid CLI token is presented to the web revoke-all route
- **THEN** the response is 401 and no revocation happens

#### Scenario: Web tokens are unaffected
- **WHEN** an ordinary web token without a scope claim is presented to a web route
- **THEN** it is accepted as before

### Requirement: CLI routes accept only CLI tokens
Every CLI route except connect SHALL accept only unexpired, correctly signed tokens whose scope is `cli` and which carry a subject, an integer generation, a device id, a hostname, and an operating system. Any other token SHALL be rejected with HTTP 401 and error code INVALID_CLI_TOKEN.

#### Scenario: Web token on a CLI route
- **WHEN** an ordinary web token is presented to a CLI route
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN

#### Scenario: Attachment token on a CLI route
- **WHEN** a public attachment token is presented to a CLI route
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN

#### Scenario: Expired token
- **WHEN** a CLI token past its expiry is presented
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN

#### Scenario: Tampered token
- **WHEN** a CLI token whose payload or signature was altered is presented
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN

#### Scenario: Missing or malformed claims
- **WHEN** a correctly signed token with scope `cli` lacks a required claim or carries a non-integer generation
- **THEN** the response is 401 with error code INVALID_CLI_TOKEN

#### Scenario: Missing credentials
- **WHEN** a CLI route is called without a bearer token
- **THEN** the response is 401

### Requirement: Token problems are always 401
Any problem with the token itself, meaning signature, expiry, scope, claims, or revocation, SHALL produce HTTP 401 and never HTTP 403, so clients can treat 401 as "this token is unusable" and treat 403 as "this token may not do that".

#### Scenario: Revoked token
- **WHEN** a revoked CLI token is presented
- **THEN** the response is 401 and not 403

#### Scenario: Wrong scope
- **WHEN** a token of the wrong scope is presented to a CLI route
- **THEN** the response is 401 and not 403

### Requirement: Tokens are checked against the owner's current revocation state
On every authenticated CLI request the system SHALL load the token's owner and compare the token's generation with the owner's current generation. A mismatch SHALL be rejected with HTTP 401 and error code CLI_ACCESS_REVOKED.

#### Scenario: Matching generation
- **WHEN** a token's generation equals its owner's current generation
- **THEN** the request proceeds

#### Scenario: Revoked after issue
- **WHEN** the owner revokes all CLI access after a token was issued
- **THEN** the next request with that token is rejected with 401 and error code CLI_ACCESS_REVOKED

#### Scenario: Issued after revocation
- **WHEN** the owner connects a new device after revoking all CLI access
- **THEN** the new token works on every CLI route

#### Scenario: Every route checks
- **WHEN** a revoked token is presented to the chat listing, either notify route, or the CLI revoke route
- **THEN** each responds 401 with error code CLI_ACCESS_REVOKED

### Requirement: Merged-away owners fail as not found
If the owner named by a CLI token no longer exists, the request SHALL fail with HTTP 404 and error code USER_NOT_FOUND. A profile merge SHALL NOT invalidate the surviving profile's CLI tokens unless the casualty's revocation generation was higher.

#### Scenario: Owner merged away
- **WHEN** a CLI token's owner was the casualty of a profile merge (the profile folded into the other and deleted)
- **THEN** CLI requests with that token fail with 404 and error code USER_NOT_FOUND

#### Scenario: Owner survived the merge
- **WHEN** a CLI token's owner survived a profile merge with a casualty of the same or a lower revocation generation
- **THEN** CLI requests with that token keep working

### Requirement: User-scoped CLI routes act only for the token's owner
A CLI route that names a user id SHALL reject any id other than the token's owner with HTTP 403 and error code NOT_TARGET_USER, and SHALL NOT perform any action.

#### Scenario: Another user's id
- **WHEN** a valid CLI token is used with a different user's id in the path
- **THEN** the response is 403 with error code NOT_TARGET_USER and nothing is revoked or sent

#### Scenario: Own id
- **WHEN** a valid CLI token is used with its owner's id in the path
- **THEN** the request is authorized

#### Scenario: Malformed id
- **WHEN** the path user id is not a valid identifier
- **THEN** the response is 422 with error code MALFORMED_USER_ID
