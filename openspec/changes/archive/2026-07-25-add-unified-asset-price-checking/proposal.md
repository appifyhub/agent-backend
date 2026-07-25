## Why

The assistant can convert fiat and cryptocurrency values but cannot check stock prices, forcing users to leave the conversation for a common financial lookup. Adding stock quotes through user-owned Twelve Data keys also creates an opportunity to replace the currency-specific LLM interface with one compact asset-price contract that can grow without adding one tool per asset class.

## What Changes

- Add Twelve Data as a configurable external-tool provider, including platform and encrypted per-user API keys, stock-quote tool selection, preset defaults, settings/profile API support, and OpenAPI documentation.
- Add native-currency stock quotes through Twelve Data's REST quote endpoint, then reuse the existing currency converter when a different fiat or cryptocurrency output currency is requested.
- **BREAKING** Replace the LLM-visible `get_exchange_rate` function with a unified asset-price function accepting `asset`, `currency`, optional `asset_type`, optional `amount`, and `force`.
- Infer omitted asset types from the existing supported fiat and cryptocurrency markers, otherwise treating the asset as a stock symbol; explicit types override inference.
- Apply one nine-minute cache policy to fiat, cryptocurrency, and stock prices, with `force` bypassing and refreshing both the price-service cache and the shared web-fetcher cache.
- Surface safe Twelve Data validation, ambiguity, not-found, rate-limit, provider, and empty-response failures to the LLM through the project's structured errors.
- Generalize existing currency price alerts into asset price alerts while preserving existing alert data and behavior, and add stock alerts through the same pricing path.
- Exclude multi-symbol quote batching from the initial scope; alert evaluation will deduplicate lookups and rely on the shared cache.
- Deliver the change in three commit-ready milestones, each ending in a mandatory manual-review stop before work may begin on the next milestone.

## Capabilities

### New Capabilities

- `asset-price-checking`: Unified fiat, cryptocurrency, and stock price lookup, Twelve Data configuration, native-currency conversion, caching, refresh, and structured provider-error behavior.
- `asset-price-alerts`: Generalized persisted price alerts for fiat, cryptocurrency, and stocks, including backward-compatible migration and shared quote evaluation.

### Modified Capabilities

None.

## Impact

- Affects external-tool provider/type catalogs, user persistence and mapping, token resolution, intelligence presets, settings/profile APIs, dependency injection, web fetching, currency pricing, LLM tool registration, price-alert persistence and scheduling, error codes, and OpenAPI documentation.
- Requires generated Alembic migrations for user stock-tool settings and the generalized price-alert schema. The user will run the repository migration generator and, after approval, the migration apply script.
- Adds no Python SDK dependency; Twelve Data is called through the existing tracked web-fetching path so caching, retries, usage accounting, spending checks, and error handling remain centralized.
- Twelve Data BASIC usage is based on each user's personal key, with existing sponsor/platform credential fallback behavior retained.
