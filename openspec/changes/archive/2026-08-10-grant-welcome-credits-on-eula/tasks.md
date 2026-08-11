## 1. Configuration

- [x] 1.1 Add `welcome_credit_grant_amount: float` (default `500.0`) and `welcome_credit_grant_eligibility_days: int` (default `7`) fields and env-var bindings to `util/config.py`, following the existing pattern
- [x] 1.2 Update `test/util/test_config.py` to cover both new fields with default and override cases

## 2. Caller-owned transaction support

- [x] 2.1 Add an ordered `UserRepository.get_locked_pair()` read, retain opt-in commit deferral on locked updates, and use the existing `UserRepository.save(commit=False)` path for the staged settings mutation
- [x] 2.2 Extend `UsageRecordRepository.create()` with opt-in commit deferral while preserving `commit=True` for existing callers
- [x] 2.3 Update `test/features/users/test_user_repo.py` and `test/features/accounting/usage/test_usage_record_repo.py` to verify deferred writes remain uncommitted until the caller commits and roll back with the caller transaction

## 3. Generic credit-grant operation

- [x] 3.1 Add `CreditTransferService.grant_credits(recipient, amount, commit, note=None)` accepting a persisted `User` or UUID without welcome-specific configuration or eligibility assumptions and requiring explicit transaction ownership
- [x] 3.2 Lock `THE_AGENT` and the recipient in UUID order, top up `THE_AGENT` by the caller-provided amount, execute the ordinary sender-minus/recipient-plus balance movement, stage transfer history, and commit only when explicitly requested
- [x] 3.3 Leave `THE_AGENT` with no net balance change or top-up history record while representing it as sender, payer, and owner in the ordinary transfer-history record
- [x] 3.4 Record the caller-provided amount and optional note with `uses_credits=True` and zero external and maintenance costs
- [x] 3.5 Keep the public peer-transfer path and its sponsored-user, handle-resolution, notification, and balance-validation behavior unchanged

## 4. EULA acceptance integration

- [x] 4.1 Modify `SettingsController.save_user_settings()` to read `THE_AGENT` and the recipient under ordered locks, validate activation before mutation, and derive welcome eligibility from the explicit locked-pre-update to updated EULA transition
- [x] 4.2 Inside the locked update, validate waitlist activation, apply the complete settings payload, and clear waitlist/invitation flags when activation is permitted
- [x] 4.3 For eligible acceptance, invoke `grant_credits` with the configured welcome amount, note `"Welcome"`, and `commit=False`, then commit the settings transaction unconditionally after the optional grant
- [x] 4.4 Reject omitted or `null` policy acceptance for unaccepted profiles, allow omission for already accepted profiles, and send the best-effort grant notification only after the caller-owned commit

## 5. Behavioral tests

- [x] 5.1 Update `test/features/accounting/transfers/test_credit_transfer_service.py` to cover `User` and UUID recipients, caller-provided amounts, optional notes, ordered agent/recipient locking, net-zero agent balance, explicit committed and deferred paths, rollback, notification timing, and transfer-record fields
- [x] 5.2 Update `test/api/test_settings_controller.py` to cover required first acceptance, ordinary post-acceptance settings saves, first acceptance, inclusive eligibility boundary, repeated acceptance, a stale pre-lock authorization snapshot, acceptance outside the window, and waitlist activation
- [x] 5.3 Cover persisted successful issuance and repeated-acceptance idempotency through the settings layer
- [x] 5.4 Keep the rollback test proving transfer-record failure preserves the prior EULA state, activation flags, balances, and transfer history

## 6. Documentation and verification

- [x] 6.1 Update the EULA-acceptance description in `docs/open-api-docs.yaml` to document the conditional one-time welcome transfer
- [x] 6.2 Run the focused configuration, repository, transfer, settings-controller, and profile-connect tests through `pipenv`
- [x] 6.3 Run Ruff and the project spacing checker on every changed Python file
