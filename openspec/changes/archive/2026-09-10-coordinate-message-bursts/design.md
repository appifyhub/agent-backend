## Context

Before this change, Telegram and WhatsApp webhook endpoints enqueued synchronous responders through FastAPI `BackgroundTasks`. Each responder created one detached SQLAlchemy session, ingested the message, constructed `ChatAgent`, and performed command, debounce, reply-decision, LLM, and send work. `ChatAgent` slept for the configured debounce delay and independently searched message history for a newer message from the same invoker.

The application runs multiple service instances against one PostgreSQL database. Process-local cancellation or locking therefore cannot establish a single burst winner. Database sessions must not remain checked out while waiting or while external services block. See `proposal.md` for the behavioral motivation and `specs/message-burst-processing/spec.md` for the required behavior.

## Goals / Non-Goals

**Goals:**

- Make PostgreSQL the authority for the active burst state and deadline.
- Keep webhook responses immediate while using a non-blocking 1 second delayed attempt.
- Preserve a strict session boundary around each short database phase.
- Pass a stable history cutoff and aggregate addressing decision into conversational processing.
- Keep the coordination mechanism small enough to share between Telegram and WhatsApp responders.

**Non-Goals:**

- Automatic retries, periodic recovery workers, or exactly-once guarantees across process failure and external platform sends.
- Platform-specific media album grouping.
- Changing command behavior, group reply probability, or LLM/tool behavior beyond invoking reply logic once per settled burst.
- Introducing Redis, a message broker, or another external dependency.

## Decisions

### Store one active burst mailbox per chat and author

Add a coordination table with a composite primary key of `(chat_id, author_id)`. A row represents outstanding conversational work rather than a permanent event log. It contains:

- a monotonically increasing `message_count`;
- `process_after`, calculated from database time plus 1 second;
- the final logical message cutoff;
- an aggregate `is_addressed` flag;
- an `is_processing` flag.

On each newly ingested non-command message, an upsert increments the message count, resets `process_after`, advances the logical cutoff when appropriate, and ORs the addressing flag. The operation returns an immutable scheduled-burst value containing the mailbox identity, message count, and wait duration.

This model is preferred over processing status on every chat message because the claimable unit is a coalesced burst, not each fragment. It also avoids accumulating completed queue rows. The mailbox row is deleted after successful processing when its message count has not advanced.

Alternative considered: add `received`, `processing`, and `completed` to every chat message. This would require grouping and transitioning several history rows for one invocation, including a separate representation for coalesced fragments, while still needing a per-author coordination lock.

### Use asynchronous delayed attempts initiated by webhooks

After the ingress transaction commits and its detached session closes, the background responder creates a DI instance containing the burst invoker and chat identifiers but no database session, then invokes its `MessageBurstService`. The suspended coroutine retains that contextual service and the immutable schedule, but no SQLAlchemy session, transaction, or checked-out connection.

After waking, it opens a new detached session and performs one atomic conditional claim. The claim succeeds only when:

- the stored message count equals the attempt's expected message count;
- `process_after` is no later than database time; and
- the mailbox is not currently being processed.

An attempt that does not satisfy those conditions closes its fresh session and exits. Every message may therefore create a small suspended coroutine, but older attempts become inexpensive no-ops. FastAPI continues returning the webhook response before these background attempts execute.

The delayed orchestration function remains asynchronous. Existing synchronous ingestion and conversational processing execute through the thread pool rather than on the event-loop thread.

Both platform responders now use the same per-scheduled-burst helper and contextual DI construction. Telegram awaits its single scheduled burst, while WhatsApp gathers the helper once for each scheduled message because one webhook may contain multiple messages.

Alternative considered: a periodic database poller. It would make recovery stronger, but it is unnecessary for the current scope and adds a continuously running subsystem. Outstanding rows can be inspected directly in the database when needed.

### Separate database phases from waiting and external work

The flow uses explicit resource boundaries:

1. Open a detached session, ingest the message, classify commands/addressing, upsert the burst mailbox, commit, and close the session.
2. Create a DI instance containing the burst invoker and chat identifiers but no database session, then await the 1 second timer.
3. Clone that contextual DI with a fresh detached session, conditionally claim the burst and its cutoff, commit, and close the session.
4. Load the bounded inputs needed for processing with fresh database access, then release that transaction before LLM, media, or platform network calls.
5. Clone the contextual DI with another short fresh transaction to finalize the mailbox after the response path completes.

The claim session is never passed into `ChatAgent`. A `MessageBurstService` created from the cloned contextual DI loads the claimed message and owns the shared processing path, preserving the resource-release discipline around long-running external operations.

### Preserve pending work that arrives during processing

A new message may arrive after an earlier message count has been claimed. Its upsert still increments the current message count and establishes a new quiet deadline without modifying the claimed cutoff.

When processing finishes, finalization compares the current message count with the claimed message count:

- If they match, delete the mailbox row.
- If they differ, clear the processing flag while retaining the newer messages and return a new scheduled-burst value for the existing deadline, with no delay if that deadline has already passed.

This completion handoff prevents newer messages from being stranded when their own delayed attempt woke while the preceding burst was still processing.

### Determine reply eligibility once per settled burst

Commands are recognized before burst upsert and continue through their immediate path. They neither wait nor change an existing conversational burst deadline.

For non-command messages, ingress contributes whether that individual message explicitly addressed the bot. The mailbox retains the logical OR across the active burst. On claim, `ChatAgent` evaluates the existing `should_reply` behavior once using the claimed cutoff and addressed state:

- private chats are addressed;
- group bursts with any explicit tag are addressed even if the final fragment is untagged;
- untagged group bursts retain the existing probabilistic/non-mention decision behavior.

Responders classify commands and record conversational messages; `MessageBurstService` owns burst coordination, claimed-message hydration, and the shared processing path. Conversational decision logic remains in `ChatAgent`.

### Add a deterministic history cutoff

Add a database-generated monotonic order column to `chat_messages`. Logical history order uses platform `sent_at` followed by this database order as a tie-breaker. The mailbox stores the final cutoff tuple for the burst, and history loading for a claimed burst is bounded by that tuple.

Every arrival resets the quiet deadline, including a late-delivered message with an earlier platform timestamp. The stored cutoff advances only to the greatest logical message tuple, allowing earlier late-delivered fragments to be included without moving the invocation past logically later chat messages.

This replaces the current ambiguous same-timestamp behavior, where differing message IDs can each be treated as newer depending on which handler evaluates them.

### Keep successful mailbox state ephemeral

Successful finalization deletes the mailbox row when its message count has not advanced.

No `completed` queue state is retained, and outstanding mailbox rows remain directly inspectable.

## Risks / Trade-offs

- [A platform delivery gap exceeds 1 second] → The later delivery forms another burst; the threshold may need adjustment if this is observed operationally.
- [One coroutine is scheduled per delivered message] → Coroutines sleep without threads or database resources, and obsolete schedules perform one short conditional check before exiting.
- [A process exits after accepting a webhook] → Outstanding mailbox state remains in the database, but automatic recovery is outside this change.
- [A process exits after sending a reply but before finalizing the mailbox] → Exactly-once recovery across the external send boundary is explicitly outside scope.
- [Active processing overlaps newer messages] → Retain the newer messages in the mailbox and schedule them when active processing finalizes.

## Migration Plan

1. Add the deterministic message-order column and active burst mailbox model, including model imports in `src/db/alembic/env.py`.
2. Have the user generate the Alembic migration with `./tools/db_generate_migration -y` and review its backfill, constraints, foreign keys, and indexes.
3. Deploy the schema before application instances that reference the new coordination table.
4. Deploy application instances with shared burst coordination and remove the old debounce path in the same application release.
5. If rollback is required, restore the old application version before removing the new table or message-order column; the additional schema is otherwise harmless to the old code.
