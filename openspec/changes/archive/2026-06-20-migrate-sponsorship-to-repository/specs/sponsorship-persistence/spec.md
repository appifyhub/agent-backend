## ADDED Requirements

### Requirement: Sponsorship repository returns domain models
The system SHALL provide a sponsorship repository that persists through the existing `SponsorshipDB` table model while accepting and returning feature-level sponsorship domain dataclasses.

#### Scenario: Fetch by composite key returns domain model
- **WHEN** a sponsorship exists for a sponsor ID and receiver ID
- **THEN** the sponsorship repository returns a sponsorship domain dataclass with the persisted field values

#### Scenario: Missing composite key returns none
- **WHEN** no sponsorship exists for a sponsor ID and receiver ID
- **THEN** the sponsorship repository returns `None`

#### Scenario: Fetch by sponsor returns domain models
- **WHEN** one or more sponsorships exist for a sponsor ID
- **THEN** the sponsorship repository returns sponsorship domain dataclasses for that sponsor

#### Scenario: Fetch by receiver returns domain models
- **WHEN** one or more sponsorships exist for a receiver ID
- **THEN** the sponsorship repository returns sponsorship domain dataclasses for that receiver

### Requirement: Sponsorship save preserves timestamp semantics
The system SHALL preserve sponsorship timestamp behavior while replacing legacy `SponsorshipSave` persistence with a domain dataclass.

#### Scenario: Save inserts pending sponsorship
- **WHEN** the sponsorship repository saves a domain dataclass with sponsor ID, receiver ID, app-defaulted `sponsored_at`, and `accepted_at = None`
- **THEN** the repository inserts a `sponsorships` row with that `sponsored_at`
- **THEN** the repository returns a domain dataclass with the persisted `sponsored_at` and null `accepted_at`

#### Scenario: Save inserts accepted sponsorship
- **WHEN** the sponsorship repository saves a domain dataclass with a non-null `accepted_at`
- **THEN** the repository inserts or updates the row with that `accepted_at`
- **THEN** the repository returns a domain dataclass with the persisted `accepted_at`

#### Scenario: Save updates acceptance without changing sponsorship time
- **WHEN** the sponsorship repository saves a domain dataclass copied from an existing sponsorship with a changed `accepted_at`
- **THEN** the repository updates `accepted_at`
- **THEN** the repository preserves the copied `sponsored_at`

#### Scenario: Save can clear acceptance
- **WHEN** the sponsorship repository saves a domain dataclass for an existing sponsorship with `accepted_at = None`
- **THEN** the repository persists null `accepted_at`
- **THEN** the sponsorship is represented as pending

### Requirement: Sponsorship deletion behavior is preserved
The system SHALL preserve existing sponsorship deletion behavior while moving persistence behind the repository.

#### Scenario: Delete existing sponsorship returns deleted snapshot
- **WHEN** the sponsorship repository deletes an existing sponsorship by sponsor ID and receiver ID
- **THEN** it removes the row
- **THEN** it returns the deleted sponsorship as a domain dataclass

#### Scenario: Delete missing sponsorship returns none
- **WHEN** the sponsorship repository deletes a missing sponsorship by sponsor ID and receiver ID
- **THEN** it returns `None`

#### Scenario: Delete all by receiver returns deleted count
- **WHEN** the sponsorship repository deletes all sponsorships for a receiver ID
- **THEN** it removes those rows
- **THEN** it returns the number of rows deleted

#### Scenario: Delete stale pending sponsorships returns deleted count
- **WHEN** the sponsorship repository deletes unaccepted sponsorships older than a cutoff
- **THEN** it removes only pending sponsorships older than the cutoff
- **THEN** it keeps accepted sponsorships and fresh pending sponsorships
- **THEN** it returns the number of rows deleted

### Requirement: Production sponsorship callers use repository domain models
The system SHALL migrate production sponsorship callers from legacy sponsorship CRUD/schema usage to the repository without changing external behavior.

#### Scenario: Sponsorship service preserves business rules
- **WHEN** sponsorship creation, acceptance, unsponsoring, self-unsponsoring, or eligibility checks run through `SponsorshipService`
- **THEN** current sponsorship business rules and result messages remain unchanged
- **THEN** sponsorship persistence uses the repository and sponsorship domain dataclass

#### Scenario: Sponsorship controller preserves API behavior
- **WHEN** sponsorship API routes fetch, create, or delete sponsorships
- **THEN** route behavior, response shape, error behavior, and authorization behavior remain externally unchanged
- **THEN** sponsorship persistence uses repository domain models internally

#### Scenario: Secondary callers preserve behavior
- **WHEN** settings, transfer validation, cleanup, chat responder, or support paths check or delete sponsorships
- **THEN** their externally visible behavior remains unchanged
- **THEN** they use repository domain models instead of legacy sponsorship CRUD/schema objects

#### Scenario: DI exposes only repository access for production sponsorship persistence
- **WHEN** production callers no longer use legacy sponsorship CRUD
- **THEN** DI exposes `sponsorship_repo` for sponsorship persistence
- **THEN** DI no longer exposes `sponsorship_crud`

#### Scenario: Legacy CRUD removed only after references are gone
- **WHEN** no production or test code imports `sponsorship_crud`, `SponsorshipCRUD`, `db.schema.sponsorship`, or `SponsorshipSave`
- **THEN** the legacy sponsorship CRUD/schema files and obsolete CRUD tests may be removed
