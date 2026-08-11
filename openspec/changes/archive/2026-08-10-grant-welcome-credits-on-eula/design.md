## Context

User profiles currently begin with a zero balance and persist EULA acceptance on the user row. EULA acceptance is irreversible, may also activate a waitlisted profile, and is saved independently of accounting operations. Credit transfers lock both user rows and commit their balance changes before creating a separately committed usage record.

`THE_AGENT` is a persisted system user. Existing transfer history represents transfers as credit-transfer usage records with the sender as payer and the receiver as counterpart. Public peer transfers require a platform handle and reject sponsored senders and receivers, while welcome issuance must work by user ID for sponsored and non-sponsored profiles.

The user creation date is stored as a calendar date. Eligibility therefore uses whole calendar-day age rather than elapsed hours.

## Goals / Non-Goals

**Goals:**
- Preserve an ordinary transfer from `THE_AGENT` as the visible accounting provenance.
- Make EULA acceptance, activation, balance changes, and transfer-history persistence atomic and idempotent.
- Reuse the ordinary credit balance and credit-transfer history semantics without applying public peer-transfer eligibility rules.
- Serialize concurrent grants to the same recipient through a recipient-row lock.

**Non-Goals:**
- Introduce promotional credit buckets, expiration, restricted spending, or special refund treatment.
- Change API-key, sponsor-key, sponsor-credit, or receiver-credit precedence.
- Backfill profiles that accepted the EULA before deployment.
- Deduplicate welcome transfers when independently activated platform profiles are later connected.
- Replace the existing `max_users` counting and admission model.
- Generalize atomic transaction ownership across unrelated accounting operations.

## Decisions

### Configure amount and per-profile eligibility window together

Add typed configuration values in `util/config.py` for:

- `WELCOME_CREDIT_GRANT_AMOUNT`, default `500.0`;
- `WELCOME_CREDIT_GRANT_ELIGIBILITY_DAYS`, default `7`.

A profile is eligible when its persisted EULA state changes from false to true and its age in whole calendar days is less than or equal to the configured window. The boundary is inclusive. Current balance, purchases, and sponsorships are deliberately excluded from eligibility because received credits are fungible and those signals do not reliably identify a new profile.

An absolute rollout cutoff was considered. The per-profile age window was chosen because it directly expresses "new profile" and naturally excludes older unaccepted records. Profiles that accepted before deployment remain ineligible because there is no false-to-true transition.

### Add a generic credit-grant operation to the transfer service

Add `grant_credits(recipient, amount, commit, note=None)` to the existing credit transfer service rather than routing issuance through its public peer-transfer method. The required `commit` flag makes transaction ownership explicit at the production callsite. The recipient may be a persisted `User` or UUID. The operation locks `THE_AGENT` and the recipient in UUID order, adds the caller-provided amount to `THE_AGENT`, immediately moves that amount through the ordinary sender-minus/recipient-plus balance operation, and records the caller-provided note. With `commit=True`, it commits and sends a best-effort post-commit notification. With `commit=False`, it leaves both the commit and subsequent `notify_grant` call to the transaction-owning caller.

The operation has no EULA, age-window, welcome-configuration, sponsorship, handle-resolution, or peer-transfer eligibility knowledge. This makes it reusable by future administrative APIs or tools while preserving user-visible provenance through the existing credit-transfer history model.

### Own one transaction across acceptance and issuance

The user-settings layer owns welcome eligibility and stages the EULA update before invoking the generic grant operation. The combined flow shall:

1. lock `THE_AGENT` and the recipient in UUID order and read the recipient's current persisted EULA and creation state;
2. if the request would transition an unaccepted waitlisted profile, validate activation capacity before applying any settings changes;
3. apply the complete settings payload and, when activation is permitted, clear the waitlist and invitation flags;
4. determine welcome eligibility from the explicit persisted-false to updated-true EULA transition and the locked creation date;
5. persist the updated recipient without committing;
6. when eligible, call `grant_credits` with the updated recipient, configured welcome amount, note `"Welcome"`, and `commit=False`; the operation reuses the same transaction and lock order, temporarily credits `THE_AGENT`, executes the ordinary balance transfer, and stages transfer history;
7. commit the settings transaction unconditionally after the optional grant;
8. when eligible, send the best-effort grant notification after the caller-owned commit succeeds;
9. roll back the transaction if any validation, settings, balance, history, or commit operation fails.

`THE_AGENT` remains the accounting source in transfer history. Its temporary top-up and transfer debit happen in the same transaction, so its final balance is unchanged and the top-up has no separate history record. Both rows use ordered pair locking. Repository and grant operations support explicit commit deferral while retaining their existing committed behavior where requested.

### Use the irreversible EULA transition as the issuance marker

The persisted false-to-true EULA transition is the one-time issuance marker. Repeated or concurrent requests re-read the row after acquiring the lock; only the request that observes false may issue the transfer. No balance or purchase heuristic is used.

A separate grant marker was considered but rejected as unnecessary while EULA acceptance cannot be revoked or reset. If policy versioning later permits resetting acceptance, a durable welcome-grant identifier must be introduced before that reset ships.

Before the first acceptance, the settings endpoint rejects payloads that omit policy acceptance so account setup cannot precede the required EULA action. `false` remains invalid for every profile. After acceptance, an omitted or `null` payload value retains normal PATCH semantics and leaves the persisted `true` state unchanged.

### Record an ordinary transfer

For an eligible acceptance, create the same transfer-history shape used by peer transfers:

- sender, payer, and owner: `THE_AGENT`;
- receiver/counterpart: the activated profile;
- purpose: credit transfer;
- amount/total credit cost: configured welcome amount;
- note: `"Welcome"`;
- credit use: true;
- external tool costs and maintenance fee: zero.

The record is visible from both the system agent and receiver transfer-history queries. The recipient's resulting balance is the existing undifferentiated credit balance.

### Preserve additive profile merging

Welcome eligibility and idempotency are per platform profile. If two profiles independently accept the EULA while eligible, each receives a transfer. Existing profile connection behavior sums their balances without recognizing or removing either transfer.

## Risks / Trade-offs

- **[Policy acceptance is reused as the idempotency marker]** → Keep acceptance irreversible; introduce a dedicated issuance marker before any future policy-version reset.
- **[Calendar-date storage makes the window coarser than elapsed time]** → Define and test eligibility in inclusive whole calendar days, matching the persisted data.
- **[Hidden transaction ownership could prematurely commit staged caller changes]** → Require an explicit `commit` argument on every grant and use `commit=False` when settings owns the transaction.
- **[Changing repository commit control can accidentally alter existing transactions]** → Make caller-owned commits opt-in and retain current defaults; cover both deferred and existing paths.
- **[A database failure could otherwise leave acceptance without history or balance]** → Keep all database mutations under one transaction and test rollback at the transfer-record boundary.
- **[Notification can fail after commit]** → Treat notification as best-effort; committed credits and history remain authoritative.
- **[Concurrent activation capacity checks remain count-based]** → Ordered pair locking prevents duplicate welcome issuance and grant deadlocks but does not redefine the existing admission model.

## Migration Plan

1. Deploy the new configuration defaults and transactional grant path together.
2. Do not modify existing balances and do not create transfer records for profiles whose EULA is already accepted.
3. Profiles whose EULA is still unaccepted are eligible only when their calendar-day age is within the configured window at acceptance.
4. Rollback disables future welcome transfers. Already committed transfers and balances remain ordinary user funds and are not reclaimed.
