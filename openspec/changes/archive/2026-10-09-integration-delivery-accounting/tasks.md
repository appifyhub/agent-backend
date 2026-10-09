## 1. Milestone 1 — delivery pricing and identities

- [x] 1.1 Add explicit Telegram and WhatsApp platform pricing.
- [x] 1.2 Resolve WhatsApp prices by the most-specific recipient prefix with an explicit default market and upward tenth-credit rounding.
- [x] 1.3 Add stable delivery purpose, tool, and provider identities without exposing delivery providers as model choices or user API-key providers.
- [x] 1.4 Cover pricing, missing configuration, market precedence, rounding, free transport, and identity behavior in existing test modules.

## 2. Milestone 2 — delivery usage persistence

- [x] 2.1 Add recipient `counterpart_id` and delivery reconciliation state to the existing usage model/domain/API mapping.
- [x] 2.2 Add latest unreconciled delivery lookup, paid reconciliation, and zero-cost reconciliation with row locking.
- [x] 2.3 Preserve ordinary usage retention and avoid new delivery/callback tables.
- [x] 2.4 Cover repository lookup, locking, cost delta, reconciliation state, and retention behavior in existing test modules.

## 3. Milestone 3 — spending-layer delivery accounting

- [x] 3.1 Charge every positive-cost non-agent recipient, including the payer when the payer is also a recipient.
- [x] 3.2 Create one delivery usage row per charged recipient and atomically update the payer by the total.
- [x] 3.3 Reconcile regular delivery without a balance change and free delivery by zeroing the row and refunding its payer.
- [x] 3.4 Cover private payer/recipient identity, group recipient totals, agent exclusion, and paid/free reconciliation in existing spending tests.

## 4. Milestone 4 — accepted-send SDK charging

- [x] 4.1 Charge through the shared successful-message storage boundary after accepted Telegram SDK sends.
- [x] 4.2 Charge through the shared successful-message storage boundary after accepted WhatsApp SDK sends.
- [x] 4.3 Cover text, media, links/buttons, and direct burst/error sends without charging reactions or non-message actions.
- [x] 4.4 Cover matching Telegram and WhatsApp SDK behavior in their existing test modules.

## 5. Milestone 5 — sequential WhatsApp sent reconciliation

- [x] 5.1 Parse defensive nullable/empty WhatsApp status batches and recognized pricing payloads.
- [x] 5.2 Reconcile only `sent` statuses sequentially by chat and destination recipient.
- [x] 5.3 Preserve regular estimates, zero/refund recognized free pricing, and ignore unsupported, non-sent, or unmatched statuses.
- [x] 5.4 Cover private and group recipient reconciliation in existing responder and repository tests.

## 6. Milestone 6 — one-message delivery preflight

- [x] 6.1 Add a spending-layer affordability check that sums the current configured prices for every positive-cost non-agent recipient.
- [x] 6.2 Require the full one-message total, such as 2.0 for recipients priced at 0.4, 0.7, and 0.9, without debiting credits or creating usage.
- [x] 6.3 Keep the affordability check stateless; do not store payer/chat approval in `SpendingService`, `DI`, or another service instance.
- [x] 6.4 Update existing spending tests for funded/unfunded private delivery, full group totals, zero-price Telegram, and current-balance rechecking.
- [x] 6.5 Run focused spending tests, an actual affordability smoke, Ruff, and spacing checks; stop for user review before wiring callers.

## 7. Milestone 7 — preflight execution wiring

- [x] 7.1 Run delivery preflight in the normal chat execution after the reply decision and before authorization errors, models, or tools can send messages.
- [x] 7.2 Run delivery preflight before immediate command processing, with an independent current-balance check for each command.
- [x] 7.3 Run delivery preflight at standalone system-announcement, cached-alert, developer-announcement, and release-announcement owners before target-specific paid work; warn and skip insufficiently funded best-effort notifications without failing their parent jobs.
- [x] 7.4 Keep all SDK methods stateless and unchanged: no affordability recheck before provider submission and no change to accepted-send charging.
- [x] 7.5 Update existing chat-agent, burst, announcement, and responder tests for BYOK blocking, direct notifications, best-effort skips, multiple nested sends, independent commands, and no paid warning submission.
- [x] 7.6 Run focused tests and real private/group/direct-notification smoke scenarios plus Ruff and spacing checks; stop for user review before onboarding changes.

## 7A. Milestone 7 correction — insufficient-credit response policy

- [x] 7A.1 Replace the insufficient-credit warning-only return with a `MessageBurstService` response policy that has the existing DI, invoker, chat, and triggering message ID.
- [x] 7A.2 Reuse known-command detection over retained inbound history, paginating until enough invoker commands are found or the retention boundary is reached; apply the one-day, seven-day, and thirty-day progression without new persistent recovery state.
- [x] 7A.3 Let an eligible command bypass only the failed delivery preflight, execute in the original invoker context, and charge every accepted response to that invoker even into overdraft; otherwise send no text and react with `👎`.
- [x] 7A.4 Keep asset, developer, and release skips as warnings; restore purchase and background media notification failures to error severity without reversing committed purchase/transfer operations.
- [x] 7A.5 Update existing burst, command, media, purchase, transfer, and announcement tests; run focused private/group/command/reaction smokes plus Ruff and spacing checks, then stop for review before onboarding.
- [x] 7A.6 Bound late private `ChatAgent` error routing to one paid message under the original owner preflight, include the `/settings` recovery command in that message, return `👎` for free reaction handling, and avoid a second settings-link send or paid fallback retry.

## 8. Milestone 8 — identical Telegram and WhatsApp account-creation grants

- [x] 8.1 In both new-account branches, save without commit, grant the configured welcome amount with existing transfer bookkeeping and no commit, then commit once.
- [x] 8.2 Keep both platform implementations identical or as close as their existing service shapes permit, without adding a single-use abstraction.
- [x] 8.3 Preserve both existing-account update branches without another grant or creation-time notification.
- [x] 8.4 Update the existing Telegram and WhatsApp inbound-service tests for the same one-time grant, transfer record, credited returned user, no notification, and rollback behavior.
- [x] 8.5 Run focused onboarding tests and first-message/settings-command smokes proving the grant is available before delivery preflight; run Ruff and spacing checks and stop for user review.

## 9. Milestone 9 — notification-only EULA acceptance

- [x] 9.1 Remove welcome-credit minting and transfer creation from EULA settings acceptance while preserving policy and waitlist locking/validation.
- [x] 9.2 After the false-to-true acceptance commit, notify the already-granted welcome amount only when the configured amount is greater than zero.
- [x] 9.3 Do not use current balance equality as the notification condition; delivery or another valid operation may already have changed the balance.
- [x] 9.4 Remove the obsolete welcome-grant eligibility-window configuration and update existing config/settings tests.
- [x] 9.5 Update existing settings tests to prove acceptance changes neither balance nor transfer records, positive grants notify once, and a zero configured grant does not notify.
- [x] 9.6 Run focused settings, transfer, and onboarding tests plus an acceptance smoke, Ruff, and spacing checks; stop for user review before contract work.

## 10. Milestone 10 — public contract, frontend handoff, and migration review

- [x] 10.1 Update the existing OpenAPI contract only for `message_delivery`, delivery identities, and `is_delivery_reconciled`; do not add README or unrelated documentation.
- [x] 10.2 Recheck the final backend behavior against `../agent-web` and create root `CHANGES.md` with all potentially frontend-affecting changes, concrete semantics, and likely frontend touchpoints.
- [x] 10.3 Include usage-purpose typing/translations, delivery tool/provider IDs and icons, hidden API-key-provider behavior, reconciliation visibility, payer/owner/counterpart semantics, and welcome-credit timing.
- [x] 10.4 Confirm `UsageRecordDB` remains registered in Alembic and ask the user to run `./tools/db_generate_migration -y`.
- [x] 10.5 Review that the generated migration only adds `usage_records.is_delivery_reconciled`, backfills existing rows as true, and leaves the final non-null default false; stop for user approval before applying it.

## 11. Milestone 11 — final verification and approved migration application

- [x] 11.1 Run the complete offline test suite and all required Ruff/spacing checks without changing reviewed behavior to satisfy incidental tests.
- [x] 11.2 Smoke the complete private and group flows: new account grant, pre-EULA delivery preflight, accepted-send debit, paid/free `sent` reconciliation, first EULA notification, zero-grant notification suppression, and independent command rejection.
- [x] 11.3 Remove only temporary smoke scaffolding and report exact verification evidence.
- [x] 11.4 Apply the reviewed migration with `./tools/db_apply_migration` only after explicit user approval.
- [x] 11.5 Stop for final review before deployment or OpenSpec archive.
