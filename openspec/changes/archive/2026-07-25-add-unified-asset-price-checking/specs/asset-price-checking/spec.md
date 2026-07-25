## ADDED Requirements

### Requirement: Twelve Data stock tool configuration
The system SHALL register Twelve Data as an external-tool provider for stock quotes, SHALL read the platform credential from `TWELVE_DATA_API_KEY`, and SHALL support encrypted per-user credentials, stock-quote tool choice, preset defaults, settings/profile transport, and the existing user/sponsor/platform credential resolution order.

#### Scenario: User-owned credential is available
- **WHEN** a user with a configured Twelve Data API key requests a stock price
- **THEN** the stock quote SHALL use that user's credential and existing user-funded tool accounting

#### Scenario: User-owned credential is absent
- **WHEN** a stock price is requested without a usable per-user Twelve Data credential
- **THEN** the system SHALL apply the existing sponsor and platform credential fallback rules for the selected stock-quote tool

#### Scenario: System agent uses a platform credential
- **WHEN** the deterministic foreground or background system agent resolves an external tool
- **THEN** the system SHALL use the corresponding platform credential without requiring credits or a duplicate credential in the agent's persisted user row

#### Scenario: Settings round trip
- **WHEN** a user saves or retrieves external-tool settings
- **THEN** the Twelve Data credential and stock-quote tool choice SHALL round-trip through the domain, persistence, profile merge, API mapping, and documented API schema without exposing decrypted secrets

### Requirement: Unified asset-price tool
The system SHALL expose one LLM-visible asset-price function with `asset` and `currency` as required parameters and `asset_type`, `amount`, and `force` as optional parameters. The supported asset types SHALL initially be `fiat`, `crypto`, and `stock`; unsupported future types such as `commodity` SHALL be rejected until implemented.

#### Scenario: Unit price is requested
- **WHEN** the LLM calls the function without `amount`
- **THEN** the system SHALL calculate and return the value for one unit of the asset

#### Scenario: Amount is requested
- **WHEN** the LLM supplies a valid numeric `amount`
- **THEN** the system SHALL return the unit price and the requested amount's total value in the requested currency

#### Scenario: Existing currency conversion
- **WHEN** the asset is fiat or cryptocurrency
- **THEN** the unified function SHALL preserve the existing fiat-to-fiat, crypto-to-crypto, fiat-to-crypto, and crypto-to-fiat conversion behavior

#### Scenario: LLM function catalog
- **WHEN** the unified asset-price function is registered
- **THEN** the currency-specific `get_exchange_rate` function SHALL no longer be exposed to the LLM

### Requirement: Optional asset-type inference
The system SHALL normalize asset markers and SHALL honor an explicitly supplied `asset_type`. When `asset_type` is omitted, the system SHALL infer `fiat` for a marker in `SUPPORTED_FIAT`, otherwise infer `crypto` for a marker in `SUPPORTED_CRYPTO`, and otherwise infer `stock`.

#### Scenario: Explicit stock resolves a colliding symbol
- **WHEN** `asset_type` is `stock` for a symbol that also appears in a fiat or cryptocurrency marker list
- **THEN** the system SHALL route the request as a stock quote

#### Scenario: Omitted known currency type
- **WHEN** `asset_type` is omitted and the normalized marker is in a supported currency list
- **THEN** the system SHALL route the request according to fiat-first and then cryptocurrency inference

#### Scenario: Omitted unknown type
- **WHEN** `asset_type` is omitted and the normalized marker is absent from both supported currency lists
- **THEN** the system SHALL treat the marker as a stock symbol and allow Twelve Data to validate it

#### Scenario: Invalid explicit type
- **WHEN** the caller supplies an asset type outside `fiat`, `crypto`, or `stock`
- **THEN** the system SHALL return a structured validation error

### Requirement: Native-currency stock quote
The system SHALL fetch a stock through Twelve Data's REST quote endpoint using a simple symbol or an exchange-qualified symbol, SHALL retain the provider's resolved symbol/exchange identity, and SHALL treat the returned quote currency as the stock's native currency.

#### Scenario: Native currency requested
- **WHEN** the requested currency equals the stock quote's native currency
- **THEN** the system SHALL return the stock price without an additional currency-provider request

#### Scenario: Different currency requested
- **WHEN** the requested currency differs from the stock quote's native currency
- **THEN** the system SHALL use the existing exchange-rate service to convert the unit price and amount into the requested supported fiat or cryptocurrency

#### Scenario: Exchange-qualified symbol
- **WHEN** the caller supplies a stock symbol with an exchange qualifier
- **THEN** the qualifier SHALL be forwarded to Twelve Data and included in the normalized stock identity

#### Scenario: Stock result metadata
- **WHEN** a stock quote succeeds
- **THEN** the result SHALL include the asset type, provider-resolved symbol, native price and currency, requested currency, converted unit price and value, amount, exchange or MIC when supplied by the provider, quote timestamp, and market-open status

### Requirement: Nine-minute price caching
The system SHALL use a nine-minute cache lifetime for fiat, cryptocurrency, and stock price data across the unified pricing path.

#### Scenario: Cached request
- **WHEN** `force` is false and an unexpired normalized price or web response exists
- **THEN** the system SHALL return cached data without making a provider request

#### Scenario: Forced refresh
- **WHEN** `force` is true
- **THEN** the request SHALL bypass both the price-service cache and the shared web-fetcher cache, make the required provider request or requests, and replace the relevant cache entries

#### Scenario: LLM refresh guidance
- **WHEN** the LLM is given the unified function schema
- **THEN** the `force` parameter description SHALL instruct it to use `true` only when the user explicitly asks for a refresh

### Requirement: Structured stock-provider failures
The system SHALL validate every Twelve Data response, SHALL guard null and empty responses, and SHALL translate failures into project structured errors with dedicated error codes while preserving a safe provider-supplied message for the LLM.

#### Scenario: Invalid, unknown, or ambiguous symbol
- **WHEN** Twelve Data rejects a stock marker or requires a more specific exchange-qualified symbol
- **THEN** the system SHALL return a `ValidationError` or `NotFoundError` whose safe message communicates the provider's resolution guidance

#### Scenario: Rate limit
- **WHEN** Twelve Data reports an exhausted rate or credit allowance
- **THEN** the system SHALL return a `RateLimitError` with a dedicated error code and safe provider context

#### Scenario: Empty or malformed provider response
- **WHEN** Twelve Data returns null, an empty object, an empty array, or a response without the required quote fields
- **THEN** the system SHALL return an `ExternalServiceError` with a dedicated error code

#### Scenario: Credential secrecy
- **WHEN** a provider or network failure is returned to the LLM or written to logs
- **THEN** the system SHALL exclude API keys, authorization headers, and other credential material

### Requirement: Single-symbol provider requests
The initial stock-price implementation SHALL request one symbol per Twelve Data quote operation.

#### Scenario: Stock quote execution
- **WHEN** one or more callers need the same normalized stock quote within the cache lifetime
- **THEN** the system SHALL serve repeated lookups through deduplication or caching and SHALL NOT require a multi-symbol provider request
