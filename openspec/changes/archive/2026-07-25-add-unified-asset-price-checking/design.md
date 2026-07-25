## Context

`ExchangeRateFetcher` currently owns fiat and cryptocurrency conversion, keeps a five-minute repository cache, and calls providers through `tracked_web_fetcher`, whose JSON cache also defaults to five minutes. The LLM exposes this as `get_exchange_rate(base_currency, desired_currency, amount)`. Currency alerts persist `base_currency` and `desired_currency` and evaluate each row through the same fetcher.

Stock quotes cross the same external-tool, user-secret, accounting, caching, settings, LLM, and alert boundaries. Twelve Data BASIC is suitable because users supply personal keys. The platform key remains a fallback under the existing user, sponsor, and platform token-resolution rules.

A significant inference constraint is that `SUPPORTED_CRYPTO` is a broad provider-derived marker list and contains stock-like symbols, including `AAPL`. Therefore omitted type inference cannot resolve every collision correctly. The explicit `asset_type` override is the authoritative path, and the LLM description must tell the model to pass the type whenever the user's intent identifies it.

## Goals / Non-Goals

**Goals:**

- Add Twelve Data stock quotes without bypassing existing credential resolution, tracking, spending validation, retries, or cache persistence.
- Expose one compact LLM price interface for fiat, cryptocurrency, and stock assets.
- Preserve amount-based currency conversion and existing cross-fiat/crypto behavior.
- Use stock-native currency as the quote source and compose conversion only when needed.
- Make cache freshness and forced refresh consistent across the whole price path.
- Surface useful, safe Twelve Data errors through structured project errors.
- Evolve existing currency alerts into generalized asset alerts without losing data or authorization semantics.
- Keep each of three milestones independently reviewable and commit-ready.

**Non-Goals:**

- Commodity pricing or exposing `commodity` as an accepted type.
- Multi-symbol Twelve Data requests.
- A separate stock-alert subsystem alongside the current price-alert subsystem.
- Real-time streaming quotes, order books, trading, portfolio management, or guaranteed exchange-session scheduling.
- Installing `twelvedata-python` or another provider SDK.

## Decisions

### 1. Model stocks as a dedicated external-tool purpose

Add a `TWELVE_DATA` provider, a `TWELVE_DATA_STOCK_QUOTE` definition, and `ToolType.api_stock_quote`. Add the platform `SecretStr` configuration field backed by `TWELVE_DATA_API_KEY`, encrypted `twelve_data_api_key` user persistence, and `tool_choice_api_stock_quote` across the same domain, mapper, preset, resolver, settings, profile-connect, and OpenAPI paths as the fiat and cryptocurrency choices.

This keeps fiat, cryptocurrency, and stock provider selection independent. A generic `api_asset_price` choice would force one selected provider to cover unrelated asset classes.

The deterministic foreground and background system agents use platform credentials directly without requiring credits or duplicating platform secrets in their persisted user rows. Their nullable tool choices continue to follow the current intelligence-preset defaults.

Alternative considered: extend `ExchangeRateFetcher` and reuse a currency tool type. Rejected because stock symbols, provider credentials, quote metadata, and errors are not currency-pair concerns.

### 2. Call Twelve Data REST directly through the tracked web fetcher

`StockQuoteFetcher` will resolve the configured stock tool and credential, build a `ConfiguredTool`, and call Twelve Data's `/quote` endpoint through `tracked_web_fetcher`. The quote endpoint is preferred to `/price` because native currency, exchange/MIC, timestamp, market-open state, previous close, and daily change are useful for normalization and errors.

No provider SDK will be installed. The official client ultimately uses its own HTTP session by default; adapting it would add indirection for one endpoint while risking bypass of the project's fetch retries, caching, usage tracking, spending checks, and structured error conventions.

The API credential will be passed only through the provider-supported request field, held as `SecretStr`, and excluded from results and logs.

### 3. Put routing and conversion in a dedicated asset-price service

Introduce an asset-price service above `ExchangeRateFetcher` and `StockQuoteFetcher`. Its normalized input is:

```text
asset: str
currency: str
asset_type: fiat | crypto | stock | omitted
amount: numeric string | omitted
force: bool
```

The LLM wrapper retains `amount` as a string to match current tool argument conventions, validates it, and passes a numeric value internally. Omitted amount means `1.0`.

Routing is:

1. Normalize markers and validate an explicit type when present.
2. If omitted, test `SUPPORTED_FIAT`, then `SUPPORTED_CRYPTO`, otherwise assume stock.
3. For fiat/crypto, delegate the asset/currency pair to `ExchangeRateFetcher`.
4. For stock, fetch the native quote. If native and requested currencies match, return it directly; otherwise obtain the native-to-requested rate from `ExchangeRateFetcher` and multiply.

The LLM function will be named `get_asset_price` and will replace `get_exchange_rate`. Its description will encourage explicit `asset_type` whenever intent is known, especially for stock/crypto symbol collisions.

Stock input accepts a simple symbol and an optional exchange qualifier. The provider-resolved MIC or exchange plus symbol becomes the internal identity, for example `XNAS:AAPL`; cache keys may prefix this as `stock:XNAS:AAPL`. The LLM does not need to construct a typed identifier because type is already a separate parameter.

Results use one normalized envelope containing asset identity/type, amount, requested currency, unit price, and total value. Stock results additionally retain native price/currency, provider, exchange/MIC, quote timestamp, and market status. This gives callers the conversion answer without discarding source-market context.

Alternative considered: expose a second stock-only LLM function. Rejected because it increases tool-schema context and duplicates conversion behavior.

### 4. Use a nine-minute cache and propagate forced refresh end to end

Change the exchange-rate cache lifetime from five to nine minutes and explicitly pass the same lifetime to provider JSON fetches. Stock quote data uses the same lifetime.

Add a force-refresh flag to the DI `web_fetcher` and `tracked_web_fetcher` factories and to `WebFetcher`. A forced fetch skips cache reads but still writes the successful response under the normal cache key. The flag is behavior, not part of the key. The tracking decorator continues to account only for actual calls.

Propagate `force` through the asset-price service and `ExchangeRateFetcher`, including every provider leg needed for cross-currency conversion. This is necessary because bypassing only the stock service cache could still return a shared web-fetcher entry. Identity conversions remain local because no provider data exists to refresh.

The LLM schema instructs the model to set `force=true` only when the user explicitly requests refreshed data. Alert evaluation always uses `force=false`.

Alternative considered: delete cache entries before a forced request. Rejected because a read-bypass/write-through flag is narrower, avoids destructive cache operations, and works for both cache layers.

### 5. Translate Twelve Data responses at the provider boundary

`StockQuoteFetcher` validates that the response is a non-empty object with the quote fields needed by the normalized result. It recognizes Twelve Data error payloads and maps invalid or ambiguous symbols, not-found results, rate limits, and provider failures to `ValidationError`, `NotFoundError`, `RateLimitError`, or `ExternalServiceError` with new dedicated error codes.

Safe provider messages are retained so the LLM can ask for an exchange qualifier or correct a symbol. API keys and request authorization material are never included. Null, empty, array, or malformed responses become `ExternalServiceError`. Caught exceptions are chained according to repository rules.

Alternative considered: let dictionary access and generic exceptions reach the existing LLM error wrapper. Rejected because it loses provider guidance and violates the project's external-response and structured-error rules.

### 6. Generalize the existing price-alert model and tools

Evolve the current `price_alerts` model rather than create a stock-specific table:

```text
chat_id
owner_id
asset_type
asset_id
currency
threshold_percent
last_price
last_price_time
```

The primary identity becomes `(chat_id, asset_type, asset_id, currency)`. Existing rows migrate from `base_currency` to `asset_id` and from `desired_currency` to `currency`; all legacy alerts use cryptocurrency bases, so the migration assigns literal `crypto` without importing runtime currency catalogs.

Rename/generalize the currency alert domain models, repository arguments, service, responder fields, and three LLM functions while preserving their count. Creation and evaluation use the asset-price service. The owner-scoped DI clone remains so each alert resolves the correct personal/sponsor/platform credential.

Within an evaluation run, group or memoize by normalized `(owner credential scope, asset_type, asset_id, currency)` where safe; the shared nine-minute cache handles remaining repeated market-data lookups. Provider batching is not required because Twelve Data charges credits per symbol and the initial use case does not require bulk quote latency optimization.

Background failures remain isolated per alert and are logged without secrets. Interactive creation and removal return structured errors to the LLM.

Alternative considered: add a parallel stock-alert service and table. Rejected because threshold calculation, authorization, ownership, delivery, and scheduling are identical.

### 7. Use generated migrations and manual gates

Each persistence milestone updates the SQLAlchemy model and confirms `src/db/alembic/env.py` imports the model before generation. Per repository policy, the user will run `./tools/db_generate_migration -y`, review the generated migration, and run `./tools/db_apply_migration` only with approval.

Each milestone ends with an unchecked STOP task. No task from the following milestone begins until the user has manually reviewed and explicitly approved the current milestone.

## Risks / Trade-offs

- [Omitted type can misclassify a colliding marker such as `AAPL` because it appears in `SUPPORTED_CRYPTO`] → Explicit type always wins; the LLM schema tells the model to send the known type, while omission remains convenient for unambiguous/legacy currency requests.
- [A nine-minute quote can be stale for fast markets] → Return provider timestamps, expose explicit forced refresh, and document that this is conversational quote checking rather than trading data.
- [Forced cross-currency stock refresh can consume multiple provider credits] → Default force to false, use it only on explicit user request, and skip conversion calls when currencies match.
- [Twelve Data BASIC quotas are small] → Prefer personal user keys, cache for nine minutes, deduplicate alert checks, and avoid batching that does not reduce per-symbol credits.
- [Renaming LLM functions is a breaking tool-contract change] → Perform it in a single milestone, update every registration/schema reference and prompt-facing description together, and validate the full tool catalog.
- [Generated alert migration changes a composite primary key] → Review generated operations and data transformation before apply; preserve all existing fields and cover migrated-row behavior.
- [Provider payloads or error formats can change] → Keep parsing at the provider boundary and fail with structured external-service errors on missing required fields.

## Migration Plan

1. Milestone 1 adds nullable user credential/tool-choice fields and provider plumbing. Confirm Alembic model imports, then have the user generate, review, and approve/apply the migration. Validate settings/profile round trips before the review stop.
2. Milestone 2 adds quote fetching and unified price routing, changes both cache layers to nine minutes, propagates forced refresh, and replaces the LLM currency function atomically. No database migration is expected.
3. Milestone 3 changes the existing alert schema and generalized code path. Confirm model imports, then have the user generate and review the data-preserving migration before approval/apply. Validate old currency alerts and new stock alerts before the review stop.

Rollback Milestone 1 by downgrading its nullable user-column migration after reverting the provider plumbing. Rollback Milestone 2 by restoring the old LLM function and cache behavior. Rollback Milestone 3 only after preserving or removing newly created stock alerts, because the old schema cannot represent them; downgrade must restore migrated currency rows to their original pair fields.

## Open Questions

None. Provider, credential ownership, interface, inference order, cache lifetime, forced-refresh semantics, SDK choice, batching scope, alert scope, and manual milestone gates have been decided.
