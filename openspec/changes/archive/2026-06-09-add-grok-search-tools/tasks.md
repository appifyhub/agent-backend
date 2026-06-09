## 1. Tool Catalog

- [x] 1.1 Add `ToolType.search` to supported Grok/xAI chat model definitions in `external_tool_library.py`.
- [x] 1.2 Add conservative xAI search cost estimates for pre-flight credit checks without using them for final billing.
- [x] 1.3 Verify xAI image tools remain excluded from search-capable tool lists.

## 2. xAI Search Execution

- [x] 2.1 Add `XAI` provider dispatch to `AIWebSearch.execute()`.
- [x] 2.2 Implement non-streaming Grok search using `xai_sdk.tools.web_search()` and `xai_sdk.tools.x_search()` in one request.
- [x] 2.3 Validate Grok search responses and raise structured `ExternalServiceError` errors for empty or unexpected responses.
- [x] 2.4 Add source formatting for xAI citations or inline citation metadata when available, while allowing answers without sources if xAI provides no source data.

## 3. Provider-Reported Cost Tracking

- [x] 3.1 Add a separate `UsageTrackingService` method for provider-reported request costs.
- [x] 3.2 Convert xAI `cost_in_usd_ticks` to credits using the existing project credit scale.
- [x] 3.3 Store the provider-reported request cost in existing usage record cost fields without introducing a migration.
- [x] 3.4 Extend `XAIUsageTrackingDecorator` to wrap the chat search call while preserving existing image tracking behavior.
- [x] 3.5 Log `server_side_tool_usage` for diagnostics without creating additional billable usage records.

## 4. Tests and Verification

- [x] 4.1 Update `test/features/web_browsing/test_ai_web_search.py` for xAI provider routing, both enabled tools, non-streaming execution, and empty-response handling.
- [x] 4.2 Update `test/features/accounting/usage/test_usage_tracking_service.py` for provider-reported cost records and maintenance fee behavior.
- [x] 4.3 Update `test/features/accounting/usage/decorators/test_x_ai_usage_tracking_decorator.py` for chat search tracking and image tracking regression coverage.
- [x] 4.4 Verify Grok search availability through xAI search provider routing coverage without adding catalog-constant assertions.
- [x] 4.5 Run the focused test files with `pipenv run`, then run `pipenv run pre-commit run --all-files --show-diff-on-failure`.
