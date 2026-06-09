## Context

The search tool currently routes configured search requests through `AIWebSearch`. That executor supports Perplexity through LangChain and Google through the Gemini SDK with `GoogleSearch` grounding. Grok/xAI models are present in the external tool library, and `xai-sdk` is already installed, but Grok models are not selectable as `ToolType.search` and `AIWebSearch` has no xAI provider branch.

xAI supports non-streaming Grok calls with server-side `web_search` and `x_search` tools enabled in the same request. The SDK exposes these tools as descriptors via `xai_sdk.tools.web_search()` and `xai_sdk.tools.x_search()`. The actual search work happens remotely during the Grok request.

xAI also returns exact provider cost through `response.usage.cost_in_usd_ticks`, where `10_000_000_000` ticks equals one US dollar. Those ticks are monetary precision units, not runtime units. The returned cost includes token charges, prompt caching effects, and server-side tool invocation costs for that request.

## Goals / Non-Goals

**Goals:**
- Make selected Grok chat models usable as configured search tools.
- Run Grok search as a single non-streaming xAI request with both web and X search tools enabled.
- Preserve the existing `AIWebSearch` call contract for callers.
- Track xAI search cost from provider-reported cost ticks instead of estimating token and tool-call costs.
- Keep pre-flight credit checks conservative using existing `CostEstimate` fields.

**Non-Goals:**
- Do not add streaming search behavior.
- Do not expose separate user-facing "web search" and "X search" modes.
- Do not add a new database column unless implementation proves existing usage record fields are insufficient.
- Do not change Google or Perplexity search behavior.
- Do not replace the separate X/Twitter API post reader.

## Decisions

1. Use one xAI branch in `AIWebSearch`.

   Add `XAI` to the provider dispatch in `AIWebSearch.execute()` and implement an xAI-specific path. The path should create an xAI chat with the configured Grok model, append the existing search prompt/query, and call `sample()` rather than `stream()`.

   Alternative considered: use the OpenAI-compatible Responses API. The installed xAI SDK already exists in the project and exposes the required tools, so using it avoids adding another client path.

2. Enable both `web_search` and `x_search` for Grok search.

   From the product perspective, the app exposes one search tool. The xAI request should therefore provide both remote search tools and let Grok decide which to call.

   Alternative considered: only enable `x_search`. That would make Grok search narrower than Google/Perplexity search and would not match the user's expectation that X search is part of the same search experience.

3. Track exact xAI cost through a separate usage tracking method.

   Add a method to `UsageTrackingService` for provider-reported request costs. It should create one usage record using the exact converted xAI cost, plus the normal maintenance fee. With the current DB shape, store the provider-reported request cost in `model_cost_credits` and keep `api_call_cost_credits` and `remote_runtime_cost_credits` at zero.

   Alternative considered: reconstruct cost from input tokens, output tokens, and server-side tool usage. xAI's own response already returns the actual billed cost after discounts and all server-side tool calls, so reconstruction would be less accurate and could double-count.

4. Keep `server_side_tool_usage` out of billing.

   The implementation may log server-side tool usage for diagnostics, but billing should use `cost_in_usd_ticks` when present.

   Alternative considered: emit separate usage records per xAI server-side tool call. This matches Google's current query-count approach but is not appropriate when xAI returns an all-inclusive provider cost.

5. Preserve existing pre-flight validation.

   Since exact xAI cost is only known after the response, Grok search models should still have approximate `CostEstimate` values sufficient for pre-flight credit validation. The estimate does not need to exactly match the final provider-reported charge.

## Risks / Trade-offs

- Provider cost metadata missing -> Treat as an external empty/unexpected response for platform-billed calls, or fall back to estimate only if the implementation deliberately accepts estimate drift.
- Exact xAI cost exceeds pre-flight estimate -> Existing spending deduction can make the payer balance negative and logs a warning; keep estimates conservative.
- Source formatting may differ from Google/Perplexity -> Prefer response citations or inline citation metadata if available; otherwise return the answer without a sources section rather than failing an otherwise valid answer.
- Existing `XAIUsageTrackingDecorator` only wraps image calls -> Extending it for chat search must avoid changing image generation accounting unintentionally.
- xAI SDK response shape may vary by model/tool output -> Add focused unit tests around cost extraction and response validation using lightweight fakes.
