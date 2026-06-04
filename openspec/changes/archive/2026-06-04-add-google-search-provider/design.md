## Context

`AIWebSearch` today is provider-agnostic by accident: it builds a LangChain chat model via `di.chat_langchain_model(configured_tool)` and calls `.invoke()`, binding no tools. This works only because Perplexity Sonar models search intrinsically, and cost is captured token-by-token in `ChatModelUsageTrackingDecorator`. Gemini does not search unless the `google_search` tool is explicitly bound, and it bills **per query**, not per token — a unit `CostEstimate` cannot express.

Verified against live APIs (scratchpad probe):
- **Perplexity** (`sonar`, `sonar-pro`, non-streaming `invoke`): `additional_kwargs["citations"]` (URLs) and `additional_kwargs["search_results"]` (`{title, url, date, snippet}`); `num_search_queries` is `None` on these tiers; `usage_metadata` has input/output/total tokens.
- **Gemini** (`gemini-flash-latest` + `google_search` via genai client): `candidates[0].grounding_metadata.web_search_queries` (list → count), `grounding_chunks[].web.{title, uri}` (title is the domain, uri is an opaque `vertexaisearch` redirect), and `usage_metadata` with `prompt_token_count`, `candidates_token_count`, and a **separate** `thoughts_token_count` not included in `candidates_token_count`.

Constraints: credit scale = 100 credits per $1; structured `util.errors` + `util.error_codes` only; no inline imports; `pipenv` for all commands.

## Goals / Non-Goals

**Goals:**
- Add Google Gemini grounding as a web-search provider and make it the default, without disturbing Perplexity's token-based math.
- Bill Gemini grounding accurately: token record (with thinking tokens) + N per-query records, maintenance fee charged once.
- Emit a shortened, deduped `Sources:` section for both providers.
- No DB migration.

**Non-Goals:**
- Reasoning-tier search models (`sonar-reasoning-pro`, `sonar-deep-research`) — they return empty content under the search token budget; not wired here.
- Unwrapping Google `vertexaisearch` redirect URLs to bare publisher URLs.
- Retrofitting Perplexity onto per-query records (its tiers don't expose a query count).

## Decisions

### 1. Provider branch inside `AIWebSearch` (mirror `simple_image_generator.py`)
`execute()` branches on `configured_tool.definition.provider`:
- `PERPLEXITY` → existing LangChain path (`di.chat_langchain_model`), unchanged token math.
- `GOOGLE_AI` → genai path via `di.google_ai_client(configured_tool)` calling `generate_content(model, contents, config=GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())]))`.
- else → `ConfigurationError(UNSUPPORTED_PROVIDER)`.

*Alternative considered*: route Gemini through LangChain (`ChatGoogleGenerativeAI.bind_tools`). Rejected — grounding metadata is awkward to reach via `response_metadata`, and the token decorator can't see the per-query count or thoughts split. The genai client gives first-class access to `grounding_metadata` and `usage_metadata`.

### 2. Reuse `GEMINI_FLASH_LATEST`; add `ToolType.search` + `web_search_query` cost
No new tool definition. Add `ToolType.search` to its `types`, and `web_search_query = 1.4` to its `CostEstimate`. Its existing token pricing (`input_1m_tokens`, `output_1m_tokens`) drives the token record.

*Alternative*: a dedicated `GEMINI_FLASH_SEARCH` tool. Rejected as redundant — same model id, and a separate tool would fragment user token resolution.

### 3. `CostEstimate.web_search_query: float | None`
New optional field = credits per single grounding query. Only consumed on the Google path. Named `web_search_query` (not `search_query`) per project preference.

### 4. Cost = one token record + N query records
On the Google path, the new tracking decorator behavior:
1. `track_text_model(...)` once — input/output tokens, maintenance fee, deduct. **Output tokens = `candidates_token_count + thoughts_token_count`** (the fix; thinking is billed as output).
2. `track_web_search_query(tool, query_count)` — emits `query_count` `UsageRecord`s, each costing `cost_estimate.web_search_query`, stored in `api_call_cost_credits`, **no maintenance fee**, then deducts each.

`query_count = len(grounding_metadata.web_search_queries or [])`. If 0 (model didn't search), no query records.

*Alternative*: reuse `track_api_call`. Rejected — it reads `api_call` (wrong field) and always adds the maintenance fee, re-introducing the N× multiplication.

### 5. Per-query fee stored in `api_call_cost_credits` (no migration)
Each query record: `model_cost_credits = 0`, `maintenance_fee_credits = 0`, `api_call_cost_credits = web_search_query`, `total_cost_credits = web_search_query`. Trade-off: grounding spend shows under "api_call" in analytics, not a dedicated bucket.

### 6. Default search → `gemini-flash-latest` in all presets
`intelligence_presets.py`: set `search = gemini-flash-latest` in all three presets. `tool_choice_resolver` still honors an explicit user choice and falls back to other configured providers (Perplexity) when Google has no token.

### 7. Sources assembly + shortening
A small helper (in `web_browsing`) normalizes per-provider sources to `(domain, url)`, then for each unique URL:
- Google: `domain = web.title`, `url = web.uri` (passed through as-is; opaque redirect).
- Perplexity: from `search_results` (fallback `citations`); `url = simplify_url(publisher_url)`; `domain = urlparse(url).netloc`.
- Shorten via `di.url_shortener(url, valid_until = now + relativedelta(months=4))`, `max_visits=None`.
- In-memory `dict[str, str]` cache (`long_url → short_url`) dedupes and avoids re-shortening.
- On shortener failure: fall back to the raw URL for that source (never fail the search).
- Append `\n\nSources:\n- [domain](short_url)\n- …` to the answer content. No cap — emit all.

## Risks / Trade-offs

- **Per-search latency**: N shortener round-trips per search → Mitigation: dedupe + in-memory cache; failures degrade to raw URLs and don't block.
- **Per-query records inflate the usage ledger** (one search → many rows) → Accepted; this is the intended audit trail and matches the vendor's billing unit.
- **Analytics blur**: grounding cost lands in `api_call_cost_credits` → Accepted for v1 to avoid a migration; can add a dedicated column later.
- **Thinking-token cost increase**: correctly counting thoughts raises Gemini cost vs. the naive path → Intended; it reflects real spend.
- **Default flip to Google**: users without a Google AI token rely on `tool_choice_resolver` fallback to Perplexity → verify fallback path resolves when Google token is absent.
- **Redirect URLs as sources**: `vertexaisearch` links are Google-branded/ugly → Accepted for v1 (no unwrapping); domain label keeps them legible.
