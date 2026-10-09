## Context

The Git index contains the authoritative reviewed foundation: file-backed platform pricing, delivery identities, one usage row per non-agent recipient, accepted-send charging in both SDKs, and sequential WhatsApp `sent` reconciliation by chat and recipient. There are no unstaged application changes.

Two required behaviors are absent from that foundation:

- delivery affordability is not checked before model work or provider submission;
- welcome credits are still granted on first EULA acceptance instead of account creation.

The recovered plan also contained provider-message-ID correlation, pricing snapshots, category corrections, failed-status refunds, callback state, and retry blocking. Those conflict with later reviewed decisions and are not part of this design.

## Goals / Non-Goals

**Goals:**

- Preserve the staged delivery behavior and schema except for the already-staged reconciliation column.
- Reject work when the payer cannot fund one complete outbound message.
- Keep preflight an affordability check only; leave all staged SDK charging and usage creation at the accepted-send boundary.
- Keep direct SDK sends covered without business-layer wrappers.
- Move the existing welcome grant and bookkeeping into new-account creation using the same transaction pattern for Telegram and WhatsApp while leaving EULA and waitlist authorization intact.
- Deliver changes in reviewable milestones and stop after each milestone.

**Non-Goals:**

- Provider-message-ID correlation or per-message lifecycle tracking.
- Monetary handling of failed, delivered, read, or played statuses.
- Category repricing, exact provider-cost lookup, or pricing-snapshot columns.
- Holds, reservations, callback inboxes, retry suppression, or automatic resend behavior.
- Deleting zeroed delivery usage, exceptional retention, or new accounting tables.
- README expansion, unrelated settings refactors, frontend implementation, or unrelated documentation.

## Decisions

### 1. Treat the staged index as the implementation baseline

The staged code remains intact unless a remaining requirement strictly needs a small change. The revised work adds preflight and onboarding behavior around that foundation rather than replacing delivery charging or reconciliation.

The original plan's message-ID and callback lifecycle machinery is deliberately discarded. Later review established that WhatsApp cost updates are processed sequentially per chat and destination recipient, that paid `sent` pricing preserves the estimate, and that free pricing zeroes and retains the usage row.

### 2. Calculate the complete one-message preflight amount in the spending layer

The spending layer will derive the affordability requirement for one outbound message from the current chat memberships:

- load every chat member;
- exclude only the platform agent;
- resolve each human recipient's private platform identifier;
- resolve each recipient price through the staged pricing service;
- sum all positive recipient prices.

For a private chat the payer is also the only human recipient. For a group the amount includes the payer and every other non-agent member, as explicitly selected during replanning. If three recipients cost 0.4, 0.7, and 0.9 credits, the payer must have at least 2.0 credits for the execution to pass preflight.

Preflight only checks affordability. It does not debit the payer, create usage records, or call or replace `charge_for_message_delivery`. The staged SDK success path remains the sole charging boundary and continues to create one usage record per positive-cost recipient after each provider-accepted message.

The check is stateless. It carries no approval cache, reservation, or accounting state in `SpendingService`, `DI`, or another service instance. The execution owner is responsible for calling it once before paid work begins. Ordinary explicit Python parameters will be used; no keyword-only `*` separator or variadic `*args` will be introduced.

Alternatives rejected:

- checking only the payer's own recipient price underfunds group delivery compared with the staged debit;
- charging during preflight would require provider-failure refunds and duplicates the existing accepted-send boundary;
- checking inside every SDK send can reject delivery after model or generation costs have already been incurred;
- passing an approval token through every SDK method and asynchronous job adds invasive plumbing that was not requested;
- persistent approval or hold tables add lifecycle and recovery work that was not requested.

### 3. Invoke stateless preflight at execution owners

The normal chat-response owner will validate delivery after deciding that a response should be produced but before authorization errors, model calls, or tools can create outbound messages. The immediate command branch will validate before command processing. This covers all text, link, media, tool, and error sends nested in that chat execution without storing approval state.

`MessageBurstService` owns an insufficient-delivery response because it already has the DI context, invoker, chat, triggering message, and provider message ID. It will not generate or send a text error. Instead it will:

- reuse `is_known_command` for the triggering message and prior retained inbound messages from the same invoker;
- paginate retained history until enough prior commands are found to decide eligibility or the configured message-retention boundary is reached, rather than trusting a bypassable fixed message count;
- allow an immediate command when no prior retained command exists, then require one day after one prior command, seven days after two, and thirty days after three or more;
- execute an eligible command in the original invoker context, bypassing only the failed delivery preflight so every provider-accepted command response is charged to the invoker and may move the balance negative;
- react to the triggering message with `👎` and send no text when the request is not a known command or the command is still within its cooldown.

The command allowance uses existing retained chat history only. It adds no recovery fields or message-ID plumbing, and naturally resets as command history crosses the configured cleanup boundary. `👎` is already allowed by both Telegram and WhatsApp; money-bag, hourglass, cross-mark, and skull reactions are not in the shared platform allowlists.

Late `ChatAgent` errors remain covered by the execution's original owner-level preflight. A second affordability check would contradict the accepted bounded-overdraft behavior after work begins and is unnecessary for the same private recipient. When a private destination exists, error routing sends at most one paid message containing the `/settings` command and returns `👎` so `MessageBurstService` reacts to the triggering message without another paid send. A provider failure is logged and also returns only `👎`; it does not retry with paid fallback text. When no private destination exists, the agent preserves the existing inline error format and its intentional `CHAT_MESSAGE_DELIMITER` boundaries for ordinary delivery in the current chat. The separate settings-link button is removed.

Standalone notification owners validate the resolved target before target-specific paid work and before invoking `SysAnnouncementsService`, which only generates announcement text. Asset alerts, developer announcements, and release announcements are optional fanout and warn before skipping an unfunded target. Purchase accounting, credit transfers, and image/video generation remain critical operations: synchronous failures propagate before work commits, while a post-commit purchase or transfer notification cannot reverse an already-completed financial operation. Purchase and background media-notification failures remain errors rather than normal warnings; transfer notification failure does not make a committed transfer fail.

Successful asynchronous image and video delivery belongs to the initiating chat execution, which validates before launching generation and is not rechecked after generation costs have been incurred. A later failure-notification attempt is a separate outbound operation, so its worker validates before generating and sending the failure text.

SDK methods remain responsible only for provider submission and accepted-send charging. They do not run affordability checks. Immediate WhatsApp commands may reuse one DI instance safely because the preflight service has no mutable approval state; each command execution invokes the check independently.

### 4. Keep preflight non-monetary and accepted-send charging atomic

Preflight performs no debit and creates no usage. For the 2.0-credit group example, it only verifies that the payer has at least 2.0 credits. Once the provider accepts a message, the existing SDK success path locks the payer, creates the three positive-cost recipient rows with `commit = False`, updates the payer by their 2.0 total, and commits through the locked user update.

One execution may submit several messages after its owner-level preflight. Each provider-accepted message is still charged by the existing SDK path. Preflight is not rerun by nested SDK sends, so prior accepted sends may have changed the balance before a later send is charged.

### 5. Use the same account-creation grant sequence on both platforms

Telegram and WhatsApp author storage already have equivalent existing-user and new-user branches. Both new-user branches will follow the same transaction sequence:

1. persist the new user without committing;
2. call the existing credit grant operation with the configured welcome amount, `Welcome` note, and `commit = False`;
3. commit the account, transfer bookkeeping, and balance together;
4. return the credited user without notifying.

The existing-user branches remain unchanged and cannot grant again. The implementations should remain identical or as close as their existing platform services permit; no new abstraction is introduced solely to remove a few duplicate transaction lines. Account creation itself is the once-only boundary and transfer bookkeeping remains authoritative history.

### 6. Make the first EULA transition notification-only

Settings handling will preserve its existing lock and validate the user, waitlist capacity, and policy transition without calling the grant operation. On the false-to-true EULA transition it will commit settings, then call the existing grant notification with the configured amount and `Welcome` note only when that amount is greater than zero.

The notification condition does not compare the user's current balance with the configured grant. The first settings response or another valid operation may have already spent credits before EULA acceptance, so balance equality would incorrectly suppress the notification. Policies cannot transition back to false, making this the only acceptance transition.

Notification happens after the settings commit. Notification failure therefore does not mint credits, roll back accepted policy state, or produce another transfer.

The obsolete age-based grant eligibility configuration and its tests are removed. There is no backfill for existing users and no change to model authorization.

### 7. Preserve the staged status contract

Only `sent` statuses with recognized `pricing.type` values participate in monetary reconciliation:

- `regular`: mark the latest pending chat-recipient delivery reconciled without changing cost or balance;
- `free_customer_service` or `free_entry_point`: set that row's delivery amount to zero and refund its payer atomically;
- all other statuses or pricing values: no monetary mutation.

Later failed-status refunds are intentionally excluded. Once a sequential row is reconciled on `sent`, a later failure cannot be matched reliably without provider-message-ID correlation, which was explicitly rejected.

### 8. Keep migration, public contract, and frontend handoff work last

The only schema migration adds the non-null `usage_records.is_delivery_reconciled` Boolean. It temporarily defaults to true so pre-delivery rows are backfilled as already reconciled, then changes the final server default to false so new delivery rows start pending. `UsageRecordDB` is already registered with Alembic. The user generates the migration only after code milestones are approved; migration application requires separate approval.

The existing API contract documentation will be updated only for the directly exposed `message_delivery` purpose, delivery identities, and reconciliation field. No README or broad architecture documentation is added.

A root `CHANGES.md` will provide the requested frontend handoff after behavior is final. It will be checked against the current `../agent-web` implementation and identify at least:

- the `message_delivery` tool-purpose union and translation requirement;
- `telegram-message-delivery`/`telegram` and `whatsapp-message-delivery`/`meta` usage identities;
- the fact that delivery-only providers are usage identities and must not appear as API-key providers or model choices;
- `is_delivery_reconciled` and its pending/paid/free meaning;
- payer, owner, and recipient `counterpart` semantics for private and group delivery rows;
- welcome-credit timing, notification behavior, and any web-visible insufficient-credit behavior;
- concrete frontend files or surfaces that may need adjustment, without editing the frontend in this backend change.

## Risks / Trade-offs

- **Concurrent executions can pass against the same balance** → This matches existing model preflight semantics; each accepted send still debits atomically through the staged SDK path.
- **Several responses can cost more than the one-message amount checked** → The owner checks once before its execution; preflight is not a debit or a per-message reservation. Every accepted message remains charged.
- **A future outbound owner could omit preflight** → Existing direct-send callsites are covered in owner-level tests; SDK methods deliberately remain accounting-only.
- **Retained command history eventually expires** → This reset is intentional; per-user backoff limits repeated emergency command responses within the retention window, while the provider account keeps a hard external spending cap against many-account abuse.
- **An eligible command can overdraw the invoker** → This is limited to retained-history eligibility and lets a user receive settings or help needed to purchase credits; later purchases first repay the negative balance.
- **A status may be out of order or refer to an older message** → Sequential per-recipient matching is an explicit product assumption; unsupported status lifecycle handling is out of scope.
- **A notification can fail after EULA commit** → Credits already exist and acceptance remains valid; existing notification error handling reports the failure without duplicating the grant.
- **Account/grant transaction failure could leave partial onboarding** → Both writes share the same session and commit boundary, with existing grant rollback behavior.

## Migration Plan

1. Review and approve each implementation milestone before starting the next.
2. After application behavior is approved, update the narrow OpenAPI contract and produce the frontend-impact `CHANGES.md`.
3. Confirm the Alembic model import and ask the user to run `./tools/db_generate_migration -y`.
4. Review that the generated migration only adds `usage_records.is_delivery_reconciled` with the intended default/nullability.
5. Run targeted behavior checks at each milestone, then the complete offline suite and changed-file quality checks at the final milestone.
6. Apply the migration only after explicit user approval, then deploy schema before application code.
7. On application rollback, retain the additive column and financial history; no delivery tables or callback state require cleanup.
