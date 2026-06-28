## ADDED Requirements

### Requirement: User Repository Domain Boundary
The system SHALL expose user persistence through a feature-level repository that returns user domain objects and keeps SQLAlchemy user rows inside the persistence layer.

#### Scenario: Fetch user by id
- **WHEN** a persisted user is fetched by UUID through the user repository
- **THEN** the repository returns a user domain object containing the persisted user data

#### Scenario: Missing user by id
- **WHEN** no user exists for the requested UUID
- **THEN** the repository returns `None`

#### Scenario: List and count users
- **WHEN** callers request a page of users or a user count
- **THEN** the repository returns domain users and the same count semantics as the legacy CRUD

### Requirement: Complete User Save Semantics
The system SHALL save complete user domain objects as full persistence state while preserving generated identity and creation metadata behavior.

#### Scenario: Save new user without id
- **WHEN** a complete user domain object without an id is saved
- **THEN** the database-generated UUID and created-at value are applied and returned in the saved domain object

#### Scenario: Save new user without connect key
- **WHEN** a complete user domain object is constructed without a connect key
- **THEN** the domain model generates a connect key before persistence

#### Scenario: Save existing user
- **WHEN** a complete user domain object with an existing id is saved
- **THEN** mutable persisted fields are replaced with the supplied domain values and the existing id and created-at value are preserved

### Requirement: Secret Field Conversion
The system SHALL represent user secret fields as domain `SecretStr` values and convert them to database storage values only at the mapper boundary.

#### Scenario: Read encrypted fields
- **WHEN** a user row containing encrypted-string fields is mapped to the domain model
- **THEN** those fields are represented as `SecretStr` values in the domain object

#### Scenario: Write encrypted fields
- **WHEN** a user domain object containing `SecretStr` fields is saved
- **THEN** the mapper writes plain secret values into the encrypted SQLAlchemy columns without exposing SQLAlchemy rows to callers

#### Scenario: Clear encrypted fields
- **WHEN** a complete user domain object has a nullable secret field set to `None`
- **THEN** saving the user clears that field in the database

### Requirement: Remote User Data Resolution
The system SHALL model Telegram and WhatsApp author payloads as remote user data and convert them to complete user domain state only after repository lookup and onboarding defaults are known.

#### Scenario: Resolve existing Telegram user
- **WHEN** Telegram remote user data matches an existing user by Telegram user id or username
- **THEN** the system preserves DB-owned user fields and applies only non-null Telegram-owned fields from the remote snapshot

#### Scenario: Resolve existing WhatsApp user
- **WHEN** WhatsApp remote user data matches an existing user by WhatsApp user id or phone number
- **THEN** the system preserves DB-owned user fields and applies only non-null WhatsApp-owned fields from the remote snapshot

#### Scenario: Preserve existing full name
- **WHEN** remote user data contains a full name and the matched user already has a full name
- **THEN** the existing full name is preserved

#### Scenario: Fill missing full name
- **WHEN** remote user data contains a full name and the matched user has no full name
- **THEN** the remote full name is applied to the user domain object

#### Scenario: Create remote user at capacity
- **WHEN** remote user data does not match an existing user and the system has reached configured capacity
- **THEN** the created user domain object is waitlisted, not invited to start, and has not accepted policies

#### Scenario: Create remote user below capacity
- **WHEN** remote user data does not match an existing user and the system has available capacity
- **THEN** the created user domain object is not waitlisted, not invited to start, and has not accepted policies

### Requirement: Platform User Lookup
The system SHALL preserve the legacy user lookup behavior for Telegram, WhatsApp, and connect-key identifiers through the user repository.

#### Scenario: Lookup Telegram user
- **WHEN** a caller looks up a user by Telegram user id or Telegram username
- **THEN** the repository returns the matching domain user or `None`

#### Scenario: Lookup WhatsApp user
- **WHEN** a caller looks up a user by WhatsApp user id or WhatsApp phone number
- **THEN** the repository returns the matching domain user or `None`

#### Scenario: Lookup connect key
- **WHEN** a caller looks up a user by connect key
- **THEN** the repository returns the matching domain user or `None`

### Requirement: Locked Credit Updates
The system SHALL preserve row-level locking semantics for user credit-balance mutations while exposing domain user objects to accounting callers.

#### Scenario: Locked single-user update
- **WHEN** a caller performs a locked update for one user
- **THEN** the repository locks the row, applies the domain update, persists it, commits it, and returns the updated domain user

#### Scenario: Locked user pair update
- **WHEN** a caller performs a locked update for two users
- **THEN** the repository locks both rows in deterministic order, maps them to the requested caller order, applies the domain update, persists both, commits them, and returns updated domain users

#### Scenario: Locked user missing
- **WHEN** a locked update references a missing user
- **THEN** the repository raises the existing user-not-found error behavior

### Requirement: Profile Connection Transaction Compatibility
The system SHALL preserve profile-connection atomicity while migrating user persistence away from legacy CRUD/schema types.

#### Scenario: Connect profiles successfully
- **WHEN** two compatible profiles are connected
- **THEN** dependent records are migrated, the casualty user is deleted, the survivor user is updated, the survivor connect key is regenerated, and all changes commit atomically

#### Scenario: Connect profiles fails
- **WHEN** a failure occurs during profile connection after the transaction begins
- **THEN** migrated dependent records, casualty deletion, survivor update, and connect-key changes are rolled back together

### Requirement: Legacy User Persistence Cleanup
The system SHALL remove legacy user CRUD and schema usage only after migrated repository/domain behavior covers production and test references.

#### Scenario: Production references migrated
- **WHEN** production code no longer imports `UserCRUD`, `db.schema.user`, `UserSave`, or `User.model_validate`
- **THEN** legacy user DI access can be removed

#### Scenario: Legacy files removed
- **WHEN** production and test reference searches are clean and repository coverage replaces legacy CRUD coverage
- **THEN** `src/db/crud/user.py`, `src/db/schema/user.py`, and obsolete user CRUD tests can be removed
