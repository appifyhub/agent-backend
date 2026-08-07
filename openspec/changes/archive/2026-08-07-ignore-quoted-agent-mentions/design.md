## Context

`ChatAgent` receives raw text for the triggering message, but its burst-aware unanswered-mention scan reads persisted `ChatMessage.text`. Inbound Telegram and WhatsApp services enrich that persisted field with replied-to and native quote content, formatting each quoted line with one or more `>>` prefixes. The current substring check does not distinguish those quote lines from newly authored text.

## Goals / Non-Goals

**Goals:**

- Give direct and burst-carried mention checks one consistent definition of non-quoted text.
- Preserve the current burst winner, agent-response chain break, command, private-chat, and random-reply behavior.
- Cover both single-level and nested formatted quotes.

**Non-Goals:**

- Changing how quotes are stored or supplied to the LLM as conversational context.
- Changing debounce timing or the scope of burst history.
- Adding database fields, migrations, or platform-specific reply rules.

## Decisions

### Derive mention-eligible text from the existing quote format

Add a small `ChatAgent` text helper that excludes lines whose first non-whitespace characters are `>>`. Mention detection will search only the remaining lines. This naturally handles both `>>` and nested `>>>>` quote prefixes while preserving unquoted lines in a mixed message.

Use this projection for direct mention detection and for each same-invoker history message examined by the unanswered-mention scan. The history scan's known-command check should inspect the same non-quoted projection so both decisions operate on newly authored text.

Alternative: persist raw and formatted text as separate message fields. That would model provenance more explicitly, but it adds a schema migration and mapper changes for information already represented deterministically by the current quote prefix.

Alternative: suppress mention carry-over whenever a message contains any quote. That would incorrectly discard a genuine direct mention written below a quote.

### Keep quote content in model context

Filtering applies only to reply eligibility. Persisted messages and LangChain history retain their full formatted quote content so the LLM can understand what the user replied to.

## Risks / Trade-offs

- A user-authored line intentionally beginning with `>>` is treated as quoted context. This matches the application's documented message format and is preferable to letting quote-shaped text trigger replies.
- Reply eligibility depends on the quote prefix remaining stable. Focused formatter and `ChatAgent` tests make that contract explicit.

## Migration Plan

No data migration is required. Deploy the reply-decision change with its regression tests; rollback consists of reverting the helper usage.
