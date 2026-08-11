## Why

New platform profiles need enough ordinary credit to try the service without configuring an API key or purchasing credits first. Tying a one-time welcome transfer to timely EULA acceptance ensures credits are issued only to newly activated profiles rather than every record that appears in the database.

## What Changes

- Add configurable welcome-credit settings for the transfer amount, defaulting to 500 credits, and the acceptance eligibility window, defaulting to 7 days after profile creation.
- On the first persisted EULA acceptance within the eligibility window, invoke a generic transactional credit-grant operation with the configured welcome amount and note `"Welcome"`.
- Record the grant as a normal credit transfer from `THE_AGENT` to the recipient; after receipt, the credits have no origin-based classification, restrictions, expiration, or spending differences.
- Keep EULA acceptance, waitlist activation changes, recipient balance mutation, and transfer-record creation in one locked database transaction.
- Make the welcome transfer available to sponsored and non-sponsored recipients without applying peer-transfer restrictions; existing sponsorship billing precedence remains unchanged.
- Grant at most once per platform profile. Connected profiles retain additive balances and may therefore contribute multiple grants after merging.
- Do not grant credits to profiles that already accepted the EULA or that first accept it after the configured post-creation eligibility window.

## Capabilities

### New Capabilities
- `welcome-credit-grants`: Configurable, one-time welcome credit transfers issued when a newly created platform profile accepts the EULA within its eligibility window.

### Modified Capabilities

None.

## Impact

- Configuration gains welcome grant amount and post-creation eligibility-window values.
- User-settings EULA acceptance decides welcome eligibility and invokes the generic credit-grant operation with welcome-specific arguments.
- Accounting and user persistence gain a transaction spanning profile activation, recipient credit issuance, and transfer-history creation.
- Credit history exposes the welcome allocation as an ordinary transfer from `THE_AGENT`.
- Existing credit spending, purchases, refunds, transfers, sponsorship billing precedence, and profile-merge balance behavior remain unchanged.
- Tests must cover eligibility boundaries, sponsored recipients, one-time/idempotent issuance, transfer history, rollback atomicity, and the generic grant API.
