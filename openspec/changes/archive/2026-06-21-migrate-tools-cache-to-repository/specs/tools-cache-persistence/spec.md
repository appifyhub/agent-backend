## ADDED Requirements

### Requirement: Tools cache domain model represents complete entry state
The system SHALL represent tools cache entries as feature-level domain dataclasses with required key, value, and creation timestamp fields plus nullable expiration state.

#### Scenario: New entry receives per-instance creation timestamp
- **WHEN** a caller creates a tools cache domain entry without specifying `created_at`
- **THEN** the entry receives a creation timestamp at instance construction time
- **THEN** separately created entries do not reuse a module-import timestamp

#### Scenario: Entry without expiration never expires
- **WHEN** a tools cache entry has `expires_at = None`
- **THEN** its expiration check returns false

#### Scenario: Entry with future expiration remains valid
- **WHEN** a tools cache entry has an expiration timestamp later than the current time
- **THEN** its expiration check returns false

#### Scenario: Entry with past expiration is expired
- **WHEN** a tools cache entry has an expiration timestamp earlier than the current time
- **THEN** its expiration check returns true

### Requirement: Tools cache keys remain deterministic and compatible
The system SHALL derive cache keys from prefix and identifier values using the existing deterministic key algorithm.

#### Scenario: Existing key output remains unchanged
- **WHEN** a caller creates a key from prefix `prefix` and identifier `identifier`
- **THEN** the result is `3fffc53e8c62753274ae6ff244f2f4a4`

#### Scenario: Same inputs produce the same key
- **WHEN** a caller creates multiple keys from the same prefix and identifier
- **THEN** every result is identical

### Requirement: Tools cache repository returns domain models
The system SHALL persist through the existing `ToolsCacheDB` table model while accepting and returning feature-level tools cache domain dataclasses.

#### Scenario: Fetch existing key returns domain model
- **WHEN** a cache entry exists for a key
- **THEN** the repository returns a tools cache domain dataclass with all persisted field values

#### Scenario: Missing key returns none
- **WHEN** no cache entry exists for a key
- **THEN** the repository returns `None`

#### Scenario: Fetch all returns domain models
- **WHEN** cache entries exist
- **THEN** the repository returns paginated tools cache domain dataclasses

### Requirement: Tools cache save performs exact full-object upsert
The system SHALL save complete cache-entry domain state through insert-or-replace behavior.

#### Scenario: Save inserts new entry
- **WHEN** the repository saves a domain entry whose key does not exist
- **THEN** it inserts the key, value, creation timestamp, and expiration timestamp exactly as supplied
- **THEN** it returns the persisted domain entry

#### Scenario: Save replaces existing entry
- **WHEN** the repository saves a domain entry whose key already exists
- **THEN** it replaces the stored value, creation timestamp, and expiration timestamp with the supplied domain state
- **THEN** it returns the updated domain entry

#### Scenario: Save can clear expiration
- **WHEN** the repository saves an existing key with `expires_at = None`
- **THEN** it persists null expiration
- **THEN** the returned domain entry never expires

### Requirement: Tools cache deletion behavior is preserved
The system SHALL preserve cache-entry deletion and expired-entry cleanup behavior behind the repository.

#### Scenario: Delete existing key returns deleted snapshot
- **WHEN** the repository deletes an existing cache key
- **THEN** it removes the row
- **THEN** it returns the deleted tools cache domain entry

#### Scenario: Delete missing key returns none
- **WHEN** the repository deletes a missing cache key
- **THEN** it returns `None`

#### Scenario: Delete expired removes only past expirations
- **WHEN** the repository deletes expired entries
- **THEN** it removes entries whose non-null expiration timestamp is earlier than the current time
- **THEN** it keeps future-expiring and never-expiring entries
- **THEN** it returns the number of deleted rows

### Requirement: Production cache consumers use repository domain models
The system SHALL migrate production tools cache consumers from legacy CRUD/schema usage to repository domain models without changing externally visible behavior.

#### Scenario: Cache consumers preserve hit and miss behavior
- **WHEN** chat, currencies, web browsing, HTML cleanup, or Twitter consumers read or write cached data
- **THEN** their cache hit, miss, expiration, value parsing, and refresh behavior remains unchanged
- **THEN** cache persistence uses repository domain models internally

#### Scenario: Scheduled cleanup preserves behavior
- **WHEN** scheduled cleanup removes expired cache entries
- **THEN** it reports the same deleted-entry count behavior
- **THEN** it uses the tools cache repository

#### Scenario: DI exposes only repository access after migration
- **WHEN** production callers no longer use legacy tools cache CRUD
- **THEN** DI exposes `tools_cache_repo` for cache persistence
- **THEN** DI no longer exposes `tools_cache_crud`

#### Scenario: Legacy persistence types are removed only after references are gone
- **WHEN** no production or test code imports `tools_cache_crud`, `ToolsCacheCRUD`, `db.schema.tools_cache`, or `ToolsCacheSave`
- **THEN** the legacy tools cache CRUD/schema files and obsolete tests may be removed
