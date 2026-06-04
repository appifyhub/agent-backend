## ADDED Requirements

### Requirement: Provider-based web search execution

The web search executor SHALL select its execution path from the configured tool's provider. Perplexity-provider tools SHALL execute via the existing LangChain chat path. Google-AI-provider tools SHALL execute via the Google genai client with the `google_search` grounding tool enabled. An unsupported provider SHALL raise a `ConfigurationError` with an `UNSUPPORTED_PROVIDER` error code.

#### Scenario: Perplexity search runs via the LangChain path
- **WHEN** a web search runs with a configured tool whose provider is Perplexity
- **THEN** the search is executed through the existing LangChain chat model path
- **AND** Perplexity token-based cost accounting is unchanged

#### Scenario: Google search runs via the genai grounding path
- **WHEN** a web search runs with a configured tool whose provider is Google AI
- **THEN** the search is executed through the Google genai client with the `google_search` tool enabled
- **AND** the grounded answer text is returned

#### Scenario: Unsupported provider is rejected
- **WHEN** a web search runs with a configured tool whose provider supports neither path
- **THEN** a `ConfigurationError` with code `UNSUPPORTED_PROVIDER` is raised

#### Scenario: Empty grounded response is guarded
- **WHEN** the Google grounding response contains no candidates or no answer content
- **THEN** an `ExternalServiceError` with an empty-response error code is raised

### Requirement: Google is the default search provider

All intelligence presets SHALL resolve the search tool type to `gemini-flash-latest` by default. The `gemini-flash-latest` tool SHALL include `ToolType.search` among its supported types. Perplexity search tools SHALL remain selectable as a fallback when the user has chosen them or when no Google AI token is available.

#### Scenario: Default search resolves to Gemini
- **WHEN** a user with a Google AI token and no explicit search tool choice triggers a web search
- **THEN** the resolved search tool is `gemini-flash-latest`

#### Scenario: Fallback to Perplexity without a Google token
- **WHEN** a user without a Google AI token but with a Perplexity token triggers a web search
- **THEN** the resolver falls back to an available Perplexity search tool

### Requirement: Answers include a shortened sources section

A successful web search SHALL append a `Sources:` section to the answer text for both providers, listing every unique source as a markdown bullet `[original-domain.com](short-url)`. There SHALL be no cap on the number of sources emitted. Duplicate source URLs SHALL be emitted only once.

#### Scenario: Google sources are listed from grounding chunks
- **WHEN** a Google grounded search returns grounding chunks
- **THEN** each chunk contributes a source whose label is the chunk's domain title and whose link is the shortened chunk URI

#### Scenario: Perplexity sources are listed from search results
- **WHEN** a Perplexity search returns `search_results`
- **THEN** each result contributes a source whose label is the publisher domain and whose link is the shortened publisher URL
- **AND** when `search_results` is absent, the bare `citations` URLs are used instead

#### Scenario: Duplicate sources are de-duplicated
- **WHEN** the same source URL appears more than once in a single search response
- **THEN** it appears only once in the `Sources:` section

### Requirement: Source URLs are shortened with graceful fallback

Every source URL SHALL be passed through the URL shortener with a validity of four months and no visit limit. Perplexity publisher URLs SHALL be cleaned of tracking parameters before shortening; Google redirect URIs SHALL be passed through unmodified. Resolved short URLs SHALL be cached in memory for the duration of the operation to avoid re-shortening duplicates. If shortening a URL fails, the raw URL SHALL be used for that source and the overall search SHALL NOT fail.

#### Scenario: A source URL is shortened
- **WHEN** a source URL is prepared for the sources section
- **THEN** it is shortened with a four-month validity and the short URL is used as the link

#### Scenario: Tracking parameters are stripped from publisher URLs
- **WHEN** a Perplexity publisher URL containing tracking parameters is prepared
- **THEN** the URL is simplified to remove tracking parameters before shortening

#### Scenario: Shortener failure falls back to the raw URL
- **WHEN** shortening a source URL raises an error
- **THEN** the raw URL is used for that source
- **AND** the search still returns its answer with the remaining sources

#### Scenario: Repeated URLs reuse the cached short URL
- **WHEN** the same long URL is shortened more than once within one operation
- **THEN** the cached short URL is reused without a second shortener call
