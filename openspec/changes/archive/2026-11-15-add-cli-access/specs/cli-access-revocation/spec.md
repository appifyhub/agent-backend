# Spec Delta

## Purpose

Let users cut off all command-line access at once, from the CLI itself or from the web settings, without exposing any internal revocation mechanics.

## ADDED Requirements

### Requirement: Revoke all CLI access from the CLI
An authenticated CLI client SHALL be able to revoke every CLI token of its owner with one request. Afterwards every token issued before the request, including the caller's, SHALL be rejected as revoked, and the request SHALL respond with status OK.

#### Scenario: Revoking from a CLI
- **WHEN** a valid CLI token calls the CLI revoke-all route for its own user
- **THEN** the response is 200 with status OK

#### Scenario: The caller is revoked too
- **WHEN** the same token is used again after revoking
- **THEN** the response is 401 with error code CLI_ACCESS_REVOKED

#### Scenario: Other devices are revoked
- **WHEN** a different device's token, issued before the revocation, is used afterwards
- **THEN** the response is 401 with error code CLI_ACCESS_REVOKED

#### Scenario: Reconnecting after revocation
- **WHEN** the owner redeems their rotated connect key after revoking
- **THEN** the new token works and the previously issued tokens remain revoked

#### Scenario: Revoking for another user
- **WHEN** a CLI token calls the revoke-all route with another user's id
- **THEN** the response is 403 with error code NOT_TARGET_USER and nothing is revoked

### Requirement: Revoke all CLI access from the web settings
An authenticated web user SHALL be able to revoke all CLI tokens of their own account with a web session token. A CLI token SHALL NOT be accepted on this route. Revocation SHALL NOT end web sessions or change the connect key.

#### Scenario: Revoking from the web
- **WHEN** a web session token calls the web revoke route for its own user
- **THEN** the response is 200 with status OK and every previously issued CLI token is rejected as revoked

#### Scenario: Another user's account
- **WHEN** a web session token calls the web revoke route with another user's id
- **THEN** the response is 403 with error code NOT_TARGET_USER and no CLI token is revoked

#### Scenario: Web session and key are untouched
- **WHEN** the owner revokes from the web
- **THEN** the web session token still works and the connect key is unchanged

#### Scenario: CLI token on the web route
- **WHEN** a CLI token calls the web revoke route
- **THEN** the response is 401 and nothing is revoked

### Requirement: Revocation is immediate and cumulative
Revocation SHALL take effect for the very next request, SHALL NOT depend on clocks or token lifetimes, and SHALL count every call: concurrent revocations SHALL NOT cancel each other.

#### Scenario: Next request is rejected
- **WHEN** a revocation completes and a request with an older token arrives immediately afterwards
- **THEN** that request is rejected as revoked

#### Scenario: Repeated revocations
- **WHEN** the owner revokes twice and connects a device between the two calls
- **THEN** the device connected in between is revoked by the second call

#### Scenario: Simultaneous revocations
- **WHEN** two revocations for the same owner run at the same time
- **THEN** both take effect and tokens issued before either are revoked

### Requirement: Revocation internals stay hidden
No API response and no user-facing text produced by this capability SHALL expose revocation counters, generations, or timestamps. Users SHALL only be offered "Revoke all CLI access".

#### Scenario: Responses carry no revocation internals
- **WHEN** a client calls the connect, revoke, chat listing, or notify routes
- **THEN** none of the responses contains a generation or revocation time

### Requirement: Profile merges keep the higher revocation generation
A profile merge SHALL give the surviving profile the higher of the two profiles' revocation generations, so that no token revoked before the merge becomes valid again.

#### Scenario: Merge with different revocation states
- **WHEN** a surviving profile and a casualty profile have different revocation generations and are merged
- **THEN** the surviving profile holds the higher of the two generations
- **AND** tokens revoked before the merge remain revoked

#### Scenario: Survivor with the higher generation
- **WHEN** the surviving profile's generation is at least the casualty's
- **THEN** CLI tokens issued for the survivor before the merge remain valid
