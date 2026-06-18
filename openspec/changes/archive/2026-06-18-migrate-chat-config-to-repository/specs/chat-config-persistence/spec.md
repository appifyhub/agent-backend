## ADDED Requirements

### Requirement: Chat config repository returns domain models
The system SHALL provide a chat config repository that persists through the existing `ChatConfigDB` table model while accepting and returning feature-level chat config domain dataclasses.

#### Scenario: Fetch by chat ID returns domain model
- **WHEN** a chat config exists for a chat ID
- **THEN** the chat config repository returns a chat config domain dataclass with the persisted field values

#### Scenario: Missing chat ID returns none
- **WHEN** no chat config exists for a chat ID
- **THEN** the chat config repository returns `None`

#### Scenario: Save inserts pure chat config
- **WHEN** the chat config repository saves a domain dataclass without a persisted `chat_id`
- **THEN** the repository inserts a `chat_configs` row using the existing database model defaults
- **THEN** the repository returns a domain dataclass with a concrete persisted `chat_id`

#### Scenario: Save updates pure chat config
- **WHEN** the chat config repository saves a domain dataclass with an existing `chat_id`
- **THEN** the repository updates that row
- **THEN** subsequent reads return the updated domain field values

### Requirement: External identifier lookup is preserved
The system SHALL preserve current chat config lookup behavior by `(external_id, chat_type)`.

#### Scenario: Existing external identifier returns domain model
- **WHEN** a chat config exists with a matching `external_id` and `chat_type`
- **THEN** the chat config repository returns that chat config as a domain dataclass

#### Scenario: Missing external identifier returns none
- **WHEN** no chat config exists with a matching `external_id` and `chat_type`
- **THEN** the chat config repository returns `None`

#### Scenario: External identifiers remain unique by chat type
- **WHEN** a chat config is created or updated
- **THEN** the existing unique database constraint for non-null `(external_id, chat_type)` remains the persistence constraint

### Requirement: Remote chat snapshots use explicit conversion
The system SHALL provide a non-null remote snapshot save flow for platform chat resolution that applies remote-owned updates when an existing chat config is found and creates from explicit defaults when no chat config is found.

#### Scenario: Existing chat merges remote-owned fields
- **WHEN** `save(ChatConfigRemoteData)` finds an existing chat config by `(external_id, chat_type)`
- **THEN** it updates remote-owned fields from non-null snapshot values
- **THEN** it preserves DB-owned fields that are not part of the remote update set

#### Scenario: Missing chat creates from remote data
- **WHEN** `save(ChatConfigRemoteData)` does not find an existing chat config by `(external_id, chat_type)`
- **THEN** it creates a new chat config from the remote snapshot and mapper defaults
- **THEN** it returns the persisted domain dataclass

#### Scenario: Missing privacy defaults to private
- **WHEN** `save(ChatConfigRemoteData)` creates a new chat config and the snapshot privacy value is `None`
- **THEN** the new chat config defaults `is_private` to `True`
- **THEN** release notifications default according to the resolved privacy value

### Requirement: Platform chat resolution preserves existing behavior
The system SHALL preserve current Telegram and WhatsApp chat config resolution behavior while moving persistence to the repository.

#### Scenario: Existing Telegram chat preserves DB-owned settings
- **WHEN** a Telegram update resolves a chat config that already exists
- **THEN** the persisted chat config keeps its existing language, reply chance, release notifications, and media mode
- **THEN** remote-owned fields such as title and non-null `is_private` refresh from the platform snapshot

#### Scenario: New Telegram chat uses explicit defaults
- **WHEN** a Telegram update resolves a chat config that does not exist
- **THEN** the new persisted chat config uses explicit defaults matching current Telegram resolver behavior

#### Scenario: Existing WhatsApp chat preserves DB-owned settings
- **WHEN** a WhatsApp update resolves a chat config that already exists
- **THEN** the persisted chat config keeps its existing language, reply chance, release notifications, and media mode
- **THEN** remote-owned fields such as title and non-null `is_private` refresh from the platform snapshot

#### Scenario: New WhatsApp chat uses explicit defaults
- **WHEN** a WhatsApp update resolves a chat config that does not exist
- **THEN** the new persisted chat config uses explicit defaults matching current WhatsApp resolver behavior

### Requirement: Repository migration preserves production behavior
The system SHALL migrate production chat config callers from legacy chat config CRUD/schema usage to the repository without changing external API behavior.

#### Scenario: Repository is added before production migration
- **WHEN** the chat config repository is added to DI
- **THEN** existing legacy CRUD callers continue to work until they are explicitly migrated

#### Scenario: Production callers use repository domain models
- **WHEN** production chat config callers are migrated
- **THEN** API controllers, authorization, domain services, platform resolvers, integrations, announcements, SDK lookup code, and responders use `chat_config_repo` and the feature-level chat config domain model
- **THEN** they do not import `db.schema.chat_config` for production chat config behavior

#### Scenario: Settings controller migration preserves API behavior
- **WHEN** settings controller chat config persistence is migrated to the repository
- **THEN** settings API routes, payloads, responses, validation behavior, and sorting remain externally unchanged

#### Scenario: DI exposes only repository access for production chat config persistence
- **WHEN** production callers no longer use legacy chat config CRUD
- **THEN** DI exposes `chat_config_repo` for chat config persistence
- **THEN** DI no longer exposes `chat_config_crud`

#### Scenario: Legacy CRUD removed only after production imports are gone
- **WHEN** no production code imports `chat_config_crud` or `db.schema.chat_config`
- **THEN** the legacy CRUD/schema files and their obsolete tests may be removed
