## 1. Cost model

- [x] 1.1 Add `web_search_query: float | None = None` to `CostEstimate` in `features/external_tools/external_tool.py`
- [x] 1.2 Add `ToolType.search` to `GEMINI_FLASH_LATEST.types` and `web_search_query = 1.4` to its `CostEstimate` in `external_tool_library.py`

## 2. Usage tracking

- [x] 2.1 Add `track_web_search_query(tool, tool_purpose, payer_id, uses_credits, query_count, runtime_seconds, is_failed=False)` to `UsageTrackingService` that emits `query_count` records, each with `api_call_cost_credits = cost_estimate.web_search_query`, `model_cost_credits = 0`, `maintenance_fee_credits = 0`, `total_cost_credits = web_search_query`
- [x] 2.2 Ensure the Gemini token record computes `output_tokens = candidates_token_count + thoughts_token_count` and `input_tokens = prompt_token_count` (extend the genai usage-stats extraction; do not touch the Perplexity/LangChain path)

## 3. Source links helper

- [x] 3.1 Add a source-link helper in `features/web_browsing/` that takes `(domain, raw_url)` pairs, dedupes via an in-memory `dict[str, str]` (`long_url → short_url`), shortens each via `di.url_shortener(url, valid_until = now + relativedelta(months=4))`, and falls back to the raw URL on `ExternalServiceError`
- [x] 3.2 Render the `Sources:` section: `\n\nSources:\n- [domain](short_url)\n- …`, emitting all unique sources (no cap)
- [x] 3.3 Normalize Perplexity sources from `additional_kwargs["search_results"]` (fallback `citations`); apply `uri_cleanup.simplify_url` to publisher URLs; derive domain via `urlparse(...).netloc`
- [x] 3.4 Normalize Google sources from `grounding_chunks[].web` using `title` as domain and `uri` as the (unmodified) URL

## 4. Search execution

- [x] 4.1 Add a Google grounding execution path (genai client via `di.google_ai_client(configured_tool)`) calling `generate_content(model, contents, config=GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())]))`; guard empty candidates/content with `ExternalServiceError`
- [x] 4.2 Wire the Google path's usage tracking: one `track_text_model` call (with the thoughts-inclusive output tokens) + one `track_web_search_query` call using `len(grounding_metadata.web_search_queries or [])`, deducting per record
- [x] 4.3 Branch `AIWebSearch.execute()` by `configured_tool.definition.provider` (Perplexity → existing path, Google AI → new path, else `ConfigurationError(UNSUPPORTED_PROVIDER)`)
- [x] 4.4 Append the `Sources:` section to the returned answer content for both providers
- [x] 4.5 Add any required DI wiring in `di/di.py` for the Google search execution path

## 5. Defaults

- [x] 5.1 Set `search = gemini-flash-latest` in all three presets in `features/external_tools/intelligence_presets.py`
- [x] 5.2 Confirm `tool_choice_resolver` falls back to Perplexity when no Google AI token is configured

## 6. Tests & verification

- [x] 6.1 Unit-test `track_web_search_query`: N records, fee placement (maintenance only on token record), per-query cost in `api_call_cost_credits`, deduction count
- [x] 6.2 Unit-test the Gemini token extraction: output = candidates + thoughts
- [x] 6.3 Unit-test the source-link helper: dedupe/cache, tracking-param stripping for publisher URLs, graceful fallback on shortener failure, sources rendering for both providers
- [x] 6.4 Unit-test `AIWebSearch` provider branching (Perplexity vs Google vs unsupported) with mocked clients — offline, no network
- [x] 6.5 Run `pipenv run pre-commit run --all-files --show-diff-on-failure` and the test suite
