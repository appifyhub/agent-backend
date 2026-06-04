## Why

Web search currently has a single effective provider: Perplexity (Sonar), reached only because Sonar models search intrinsically through the LangChain chat path. We want Google (Gemini grounding with Google Search) as a second provider — and the default — for resilience (fallback when Perplexity is down), cost optimization, and result-set diversity. The blocker is cost: Gemini grounding bills **per search query** ($14/1000 ≈ 1.4 credits/query, and one prompt can fire N queries), a unit the current token-only cost model cannot represent. Wiring Gemini through the existing path as-is would silently undercount the exact cost we care about.

## What Changes

- Add a Google (Gemini) grounding path to web search, selected by provider inside `AIWebSearch`, mirroring the provider-branch pattern in `simple_image_generator.py`. Perplexity keeps its existing LangChain path unchanged.
- Make `gemini-flash-latest` the default search tool across **all** intelligence presets; add `ToolType.search` to that tool. Perplexity remains available as a fallback.
- Introduce a per-query cost dimension `web_search_query` on `CostEstimate`, and bill a Google search as **one token record + N per-query records** (one per `web_search_queries` entry).
- Fix Gemini token accounting so output tokens include `thoughts_token_count` (thinking), which the current extraction ignores (~3× output undercount on thinking models).
- Append a `Sources:` section to the answer for **both** providers, listing every (deduped) source as `[original-domain.com](short-url)`. All source URLs are run through the existing URL shortener with a 4-month validity; shortening failures fall back to the raw URL.

## Capabilities

### New Capabilities
- `web-search`: Multi-provider web search (Perplexity + Google Gemini grounding), provider selection and default, and the appended shortened `Sources:` section.
- `web-search-cost-tracking`: Cost accounting for web search, including the per-query `web_search_query` dimension, the token-record + N query-records split, the Gemini thinking-token correction, and the maintenance-fee placement rule.

### Modified Capabilities
<!-- None — openspec/specs/ is empty; all behavior here is newly specified. -->

## Impact

- **Code**:
  - `features/web_browsing/ai_web_search.py` — provider branch + sources assembly.
  - `features/external_tools/external_tool.py` — `CostEstimate.web_search_query`.
  - `features/external_tools/external_tool_library.py` — `GEMINI_FLASH_LATEST` gains `ToolType.search` + `web_search_query` cost.
  - `features/external_tools/intelligence_presets.py` — default search → `gemini-flash-latest` in all presets.
  - `features/accounting/usage/usage_tracking_service.py` — new `track_web_search_query`; Gemini token-record extraction (incl. thoughts).
  - `features/accounting/usage/llm_usage_stats.py` (or the Google decorator) — thinking-token inclusion for the genai path.
  - `di/di.py` — wiring for the Google search execution path.
  - A small source-link helper (shorten + in-memory `long_url → short_url` cache + graceful fallback) reusing `url_shortener.py` and `uri_cleanup.simplify_url`.
- **External services**: Adds N URL-shortener calls per search (one per unique source); adds Google AI grounding spend (per-query, billed to the payer).
- **No DB migration**: per-query fee is stored in the existing `api_call_cost_credits` column.
- **Dependencies**: none new (`google-genai`, `langchain-google-genai`, URL shortener already present).
