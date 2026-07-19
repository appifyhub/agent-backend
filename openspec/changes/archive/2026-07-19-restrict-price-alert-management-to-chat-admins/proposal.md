## Why

Price alerts are shared chat state, but any chat member can currently create, reconfigure, or remove them. Management should follow the chat's existing administration boundary so ordinary members cannot change notifications delivered to the whole chat.

## What Changes

- Require current chat-administrator access to create or reconfigure a price alert.
- Require current chat-administrator access to remove a price alert.
- Continue allowing chat members to list active price alerts.
- Continue treating the owner of a private chat as its administrator for price-alert management.
- Preserve scheduled alert evaluation, delivery, persistence identity, and cleanup behavior.

## Capabilities

### New Capabilities

- `price-alert-administration`: Authorization rules for managing shared chat price alerts while retaining member visibility and private-chat ownership behavior.

### Modified Capabilities

None.

## Impact

- Price-alert service authorization and focused service tests.
- Existing chat-membership synchronization and `validate_chat_admin` behavior are reused.
- No database migration, public API change, or new dependency is expected.
