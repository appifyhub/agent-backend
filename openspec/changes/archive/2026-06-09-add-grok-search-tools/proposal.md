## Why

Users can already choose Google Gemini Flash and Perplexity models for the app's search tool, but Grok models are only available for chat/vision/image workflows. xAI now supports non-streaming server-side `web_search` and `x_search` tools in the same Grok request, which lets Grok provide search behavior through the existing user-facing search abstraction.

## What Changes

- Allow selected Grok/xAI chat models to be configured as `ToolType.search` tools.
- Add an xAI search execution path that performs one non-streaming Grok call with both `web_search` and `x_search` enabled.
- Return the Grok answer through the same `AIWebSearch` interface used by Google and Perplexity search.
- Track xAI search usage using xAI's provider-reported `cost_in_usd_ticks` value instead of estimating separate token/tool invocation costs.
- Keep rough xAI cost estimates only for pre-flight credit validation.

## Capabilities

### New Capabilities
- `grok-search-tools`: Covers using Grok/xAI models as configured search tools with server-side web and X search, including exact provider-reported cost tracking.

### Modified Capabilities

None.

## Impact

- Affected code:
  - `src/features/external_tools/external_tool_library.py`
  - `src/features/web_browsing/ai_web_search.py`
  - `src/features/accounting/usage/usage_tracking_service.py`
  - `src/features/accounting/usage/decorators/x_ai_usage_tracking_decorator.py`
  - `src/di/di.py`
- No database migration is expected if provider-reported xAI cost is stored in existing usage record cost fields.
- No new external dependency is expected; `xai-sdk` is already installed and exposes `web_search()` and `x_search()`.
