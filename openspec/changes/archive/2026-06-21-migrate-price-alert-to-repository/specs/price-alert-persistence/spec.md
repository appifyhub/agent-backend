## ADDED Requirements

### Requirement: Price-alert domain model represents complete alert state
The system SHALL represent price alerts as feature-level domain dataclasses containing their complete composite identity, ownership, threshold, observed price, and observed-price timestamp state.

#### Scenario: New alert receives per-instance price timestamp
- **WHEN** a caller creates a price-alert domain object without specifying `last_price_time`
- **THEN** the object receives a timestamp at instance construction time
- **THEN** separately created alerts do not reuse a module-import timestamp

#### Scenario: Caller supplies explicit price timestamp
- **WHEN** a caller creates a price alert with an explicit `last_price_time`
- **THEN** the domain object preserves that timestamp exactly

### Requirement: Price-alert repository preserves composite identity
The system SHALL identify persisted price alerts by chat ID, base currency, and desired currency through the existing composite primary key.

#### Scenario: Fetch existing composite identity returns domain model
- **WHEN** an alert exists for a chat, base currency, and desired currency
- **THEN** the repository returns a price-alert domain object containing all persisted fields

#### Scenario: Fetch missing composite identity returns none
- **WHEN** no alert exists for the supplied chat and currency pair
- **THEN** the repository returns `None`

#### Scenario: Different desired currency remains a distinct alert
- **WHEN** one chat stores alerts with the same base currency and different desired currencies
- **THEN** the repository persists and retrieves them as separate alerts

### Requirement: Price-alert repository returns complete domain collections
The system SHALL provide paginated all-alert queries and chat-scoped alert queries that return price-alert domain objects.

#### Scenario: Fetch all applies pagination
- **WHEN** a caller requests alerts with skip and limit values
- **THEN** the repository returns the corresponding page of domain alerts

#### Scenario: Fetch alerts for chat excludes other chats
- **WHEN** alerts exist for multiple chats
- **THEN** the chat-scoped query returns only alerts belonging to the requested chat

### Requirement: Price-alert save performs complete-state upsert
The system SHALL save complete price-alert domain state through insert-or-replace behavior.

#### Scenario: Save inserts missing alert
- **WHEN** the repository saves an alert whose composite identity does not exist
- **THEN** it inserts every domain field exactly as supplied
- **THEN** it returns the persisted domain alert

#### Scenario: Save replaces existing alert state
- **WHEN** the repository saves an alert whose composite identity already exists
- **THEN** it replaces owner, threshold, last price, and last price timestamp with the supplied state
- **THEN** it returns the updated domain alert

#### Scenario: Price refresh preserves unrelated alert state
- **WHEN** the currency-alert service refreshes a triggered alert's price
- **THEN** it preserves composite identity, owner, and threshold
- **THEN** it updates only last price and last price timestamp before saving

### Requirement: Price-alert deletion behavior is preserved
The system SHALL preserve targeted alert deletion and stale-alert cleanup behavior behind the repository.

#### Scenario: Delete existing alert returns deleted snapshot
- **WHEN** the repository deletes an existing composite identity
- **THEN** it removes the row
- **THEN** it returns the deleted price-alert domain object

#### Scenario: Delete missing alert returns none
- **WHEN** the repository deletes a missing composite identity
- **THEN** it returns `None`

#### Scenario: Delete stale alerts uses strict cutoff
- **WHEN** stale cleanup runs with a cutoff timestamp
- **THEN** it deletes alerts whose `last_price_time` is earlier than the cutoff
- **THEN** it keeps alerts at or after the cutoff
- **THEN** it returns the number of deleted rows

### Requirement: Production price-alert consumers use repository domain models
The system SHALL migrate currency-alert and cleanup consumers from legacy CRUD/schema usage to repository domain models without changing externally visible behavior.

#### Scenario: Currency-alert behavior remains unchanged
- **WHEN** callers create, list, trigger, refresh, or delete currency alerts
- **THEN** alert calculations, response models, timestamp formatting, notifications, and persistence outcomes remain unchanged
- **THEN** persistence uses price-alert domain objects internally

#### Scenario: Scheduled cleanup uses price-alert repository
- **WHEN** scheduled cleanup removes stale price alerts
- **THEN** it reports the same deleted-alert count behavior
- **THEN** it calls the price-alert repository

#### Scenario: Profile connection remains atomic
- **WHEN** profile connection reassigns price-alert ownership as part of its cross-model transaction
- **THEN** its existing direct database update remains unchanged by this migration

#### Scenario: Legacy persistence types are removed after migration
- **WHEN** no production or test code references `price_alert_crud`, `PriceAlertCRUD`, `db.schema.price_alert`, or `PriceAlertSave`
- **THEN** the legacy DI access, CRUD/schema files, SQL helper, and obsolete tests are removed
