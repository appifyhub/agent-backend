## ADDED Requirements

### Requirement: Per-query cost dimension

`CostEstimate` SHALL provide an optional `web_search_query` field expressing the credit cost of a single grounding search query. The `gemini-flash-latest` tool SHALL define `web_search_query = 1.4` credits (equivalent to $0.014 per query at 100 credits per $1).

#### Scenario: Gemini search tool carries a per-query cost
- **WHEN** the cost estimate for `gemini-flash-latest` is inspected
- **THEN** `web_search_query` equals 1.4 credits

#### Scenario: Tools without grounding leave the dimension unset
- **WHEN** a tool that does not perform grounding is inspected
- **THEN** its `web_search_query` value is unset and contributes no cost

### Requirement: Google search is billed as a token record plus per-query records

A Google grounding search SHALL produce exactly one token-usage record plus one usage record per executed search query. The query count SHALL be the number of entries in the response's `web_search_queries`. When the model executes no search queries, no per-query records SHALL be created.

#### Scenario: One token record plus N query records
- **WHEN** a Google grounded search reports two executed search queries
- **THEN** one token-usage record is created for the model tokens
- **AND** two per-query usage records are created

#### Scenario: No queries produces no query records
- **WHEN** a Google grounded search reports zero executed search queries
- **THEN** only the token-usage record is created

### Requirement: Gemini output tokens include thinking tokens

For the Google grounding path, the token record's output token count SHALL equal `candidates_token_count` plus `thoughts_token_count`. Input tokens SHALL be `prompt_token_count`.

#### Scenario: Thinking tokens are counted as output
- **WHEN** a Gemini response reports `candidates_token_count` of 282 and `thoughts_token_count` of 864
- **THEN** the recorded output token count is 1146

### Requirement: Per-query records carry only the per-query fee

Each per-query usage record SHALL cost exactly `cost_estimate.web_search_query`, stored in the `api_call_cost_credits` field, with zero model cost and zero maintenance fee. The maintenance fee SHALL be charged only once, on the token record. The per-query cost SHALL be deducted from the payer for each query record.

#### Scenario: Query record cost and fee placement
- **WHEN** a per-query usage record is created with a `web_search_query` cost of 1.4 credits
- **THEN** its `api_call_cost_credits` is 1.4, its model cost is 0, and its maintenance fee is 0

#### Scenario: Maintenance fee charged once per search
- **WHEN** a Google search produces one token record and three query records
- **THEN** the maintenance fee is applied to the token record only and not to any query record

#### Scenario: Each query record is deducted
- **WHEN** three per-query records are created for a search
- **THEN** the payer is deducted the per-query cost three times in addition to the token-record deduction
