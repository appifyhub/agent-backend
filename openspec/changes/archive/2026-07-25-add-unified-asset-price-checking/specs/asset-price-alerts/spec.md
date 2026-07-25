## ADDED Requirements

### Requirement: Generalized asset price alerts
The system SHALL generalize the existing currency-alert contract to create, remove, list, and evaluate price alerts for fiat, cryptocurrency, and stock assets without increasing the number of LLM-visible alert-management functions.

#### Scenario: Create stock alert
- **WHEN** a chat administrator creates an alert with a stock asset, requested currency, and valid threshold
- **THEN** the system SHALL resolve the current value through the unified asset-price service and persist a normalized stock alert

#### Scenario: Create currency alert
- **WHEN** a chat administrator creates an alert for a fiat or cryptocurrency asset
- **THEN** the system SHALL preserve the existing authorization, threshold, initial-price, and messaging-frequency behavior through the generalized interface

#### Scenario: Remove alert
- **WHEN** a chat administrator removes an alert using its asset type, normalized asset identity, and requested currency
- **THEN** the matching alert SHALL be deleted and returned through the generalized response model

#### Scenario: List alerts
- **WHEN** active alerts are listed for a chat
- **THEN** each result SHALL identify its asset type, normalized asset identity, requested currency, threshold, last price, and last-price time

### Requirement: Asset-aware alert persistence
Each persisted alert SHALL store `asset_type`, normalized `asset_id`, requested `currency`, threshold, last price and time, chat, and owner, and SHALL be uniquely identified by chat, asset type, asset identity, and requested currency.

#### Scenario: Exchange-qualified stock identity
- **WHEN** Twelve Data resolves a stock to an exchange or MIC
- **THEN** the alert SHALL persist an exchange-aware identity such as `XNAS:AAPL` so different listings do not collide

#### Scenario: Existing alert migration
- **WHEN** the generalized price-alert migration runs
- **THEN** every existing `base_currency` and `desired_currency` row SHALL migrate to `asset_id` and `currency`, with `asset_type` set to cryptocurrency because every legacy alert has a cryptocurrency base

#### Scenario: Migration preserves behavior
- **WHEN** a migrated currency alert is listed, evaluated, or removed
- **THEN** it SHALL retain its chat, owner, threshold, last price, last-price time, and currency-pair semantics

### Requirement: Shared cached alert evaluation
Background alert evaluation SHALL use the unified asset-price service with forced refresh disabled and SHALL evaluate each alert under its owner's scoped dependency context.

#### Scenario: Repeated quote across alerts
- **WHEN** multiple active alerts require the same normalized asset and requested currency during one evaluation run
- **THEN** the system SHALL deduplicate the lookup or reuse the shared nine-minute cache rather than consume duplicate provider credits

#### Scenario: Threshold reached
- **WHEN** the absolute percentage change from an alert's stored price meets or exceeds its threshold
- **THEN** the system SHALL emit a generalized triggered-alert result and update the stored price and timestamp

#### Scenario: Threshold not reached
- **WHEN** the absolute percentage change remains below the threshold
- **THEN** the system SHALL leave the alert's stored comparison price and timestamp unchanged

#### Scenario: One background lookup fails
- **WHEN** an individual alert's provider lookup raises a structured error
- **THEN** the evaluator SHALL log safe alert context, skip that alert, and continue evaluating remaining alerts without exposing credentials

### Requirement: Alert interface compatibility
The generalized LLM alert functions SHALL use the same asset marker, requested currency, and optional asset-type semantics as the unified asset-price function.

#### Scenario: Omitted asset type
- **WHEN** an alert function omits `asset_type`
- **THEN** the system SHALL apply the same fiat-first, cryptocurrency-second, otherwise-stock inference rules used by asset-price lookup

#### Scenario: Explicit stock type
- **WHEN** an alert function specifies `asset_type` as `stock`
- **THEN** the system SHALL resolve the marker as a stock even if it collides with a supported fiat or cryptocurrency marker

#### Scenario: Interactive provider error
- **WHEN** stock resolution fails while creating or removing an alert
- **THEN** the LLM SHALL receive the corresponding safe structured error rather than a generic failure or silent fallback
