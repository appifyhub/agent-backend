# grok-search-tools Specification

## Purpose
Define how Grok/xAI models participate in the existing search tool abstraction, including server-side web/X search execution and provider-reported cost tracking.

## Requirements
### Requirement: Grok models are selectable for search
The system SHALL allow supported Grok/xAI chat models to be configured as search tools through the existing search tool selection mechanism.

#### Scenario: Supported Grok model appears as search-capable
- **WHEN** the system builds the list of available search tools
- **THEN** supported Grok/xAI chat models are included with `ToolType.search`

#### Scenario: Unsupported xAI tools remain unavailable for search
- **WHEN** the system builds the list of available search tools
- **THEN** xAI image-generation tools are not included as search tools

### Requirement: Grok search uses web and X search in one request
The system SHALL execute Grok-backed search with one non-streaming xAI request that enables both server-side web search and X search tools.

#### Scenario: Grok search execution
- **WHEN** a user invokes the search tool with a Grok/xAI model selected
- **THEN** the system sends one non-streaming Grok request with both `web_search` and `x_search` enabled

#### Scenario: Grok search returns an answer
- **WHEN** xAI returns a non-empty search response
- **THEN** the system returns the answer through the existing AI web search result interface

#### Scenario: Empty Grok search response
- **WHEN** xAI returns no answer content for a Grok search request
- **THEN** the system raises a structured external service error

### Requirement: Grok search uses provider-reported cost
The system SHALL track Grok search usage using xAI's provider-reported per-request cost when `cost_in_usd_ticks` is available.

#### Scenario: Provider-reported cost is recorded
- **WHEN** a Grok search request succeeds and includes `cost_in_usd_ticks`
- **THEN** the system records one usage entry using the converted provider-reported cost

#### Scenario: Server-side tool usage is not double-counted
- **WHEN** a Grok search response includes server-side web or X tool usage counts
- **THEN** the system does not create additional billable usage entries for those internal tool calls

#### Scenario: Cost metadata is missing
- **WHEN** a Grok search response is missing provider-reported cost metadata
- **THEN** the system handles the response according to structured external-service error handling

### Requirement: Existing search providers are unchanged
The system SHALL preserve current Google and Perplexity search behavior while adding Grok-backed search.

#### Scenario: Google search still uses Google grounding
- **WHEN** a user invokes search with a Google search model selected
- **THEN** the system uses the existing Google search execution path

#### Scenario: Perplexity search still uses Perplexity
- **WHEN** a user invokes search with a Perplexity search model selected
- **THEN** the system uses the existing Perplexity search execution path
