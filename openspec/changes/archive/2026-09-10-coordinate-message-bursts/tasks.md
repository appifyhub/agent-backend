## 1. Persistence and Ordering

- [x] 1.1 Add deterministic ingestion ordering to `ChatMessageDB`, its domain mapper, repository ordering, and bounded-history queries.
- [x] 1.2 Add the active per-chat/per-author burst mailbox model and repository operations for upsert, conditional claim, and message-count-aware finalization.
- [x] 1.3 Register the active burst mailbox model in `src/db/alembic/env.py`.
- [x] 1.4 Generate and review the Alembic migration, including existing-row identity population, reversible constraints, foreign keys, and indexes.

## 2. Burst Orchestration

- [x] 2.1 Add shared burst orchestration that records a 1 second database deadline and returns an immutable scheduled-burst value.
- [x] 2.2 Add the asynchronous delayed attempt using the scheduled wait duration, with a context-only DI retaining the burst invoker and chat identifiers, no database session or transaction retained across the wait, and fresh short sessions for claim and finalization.
- [x] 2.3 Run synchronous ingestion and conversational processing through the thread pool so delayed orchestration never blocks the event-loop thread.
- [x] 2.4 Preserve newer messages received during active processing and schedule them after the earlier claim finalizes.

## 3. Inbound Platform Integration

- [x] 3.1 Integrate Telegram ingestion with command bypass, per-message addressing contribution, burst scheduling, and bounded conversational processing.
- [x] 3.2 Integrate WhatsApp ingestion with the same shared command and burst lifecycle.
- [x] 3.3 Ensure commands process immediately without creating or extending a conversational burst.

## 4. Chat-Agent Cutover

- [x] 4.1 Pass the claimed burst cutoff and aggregate addressed state into chat history and reply-decision behavior.
- [x] 4.2 Evaluate group non-mention behavior once per settled burst while treating private bursts and explicitly addressed group bursts as addressed.
- [x] 4.3 Remove `ChatAgent` sleep, per-message supersession comparison, ambiguous equal-timestamp handling, and all obsolete callers and tests.
- [x] 4.4 Replace the old debounce configuration path with the 1 second burst quiet-period configuration and update existing configuration tests.

## 5. Verification and Cleanup

- [x] 5.1 Extend existing repository tests for upsert, one-winner conditional claims, message-count-aware finalization, and deterministic cutoff ordering.
- [x] 5.2 Extend existing service, responder, and chat-agent tests for timer reset, obsolete timer no-op, resource release during sleep, command immediacy, group author isolation, group addressing aggregation, and private photo-plus-prompt bursts.
- [x] 5.3 Run a concurrent PostgreSQL scenario with two service-level claim attempts and verify that only the settled message count invokes conversational processing.
- [x] 5.4 Run the focused changed test modules, complete test suite, Ruff, and spacing checker on every changed Python file.
- [x] 5.5 Remove obsolete debounce helpers and confirm API documentation requires no behavior-contract update beyond the OpenSpec capability.
- [x] 5.6 Normalize PostgreSQL database timestamps to the mailbox timestamp domain and verify newer-message finalization against PostgreSQL.
- [x] 5.7 Increase the default burst quiet period to 1 second and verify late delivery remains within one settled burst.
