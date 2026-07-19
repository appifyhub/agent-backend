## Context

Price alerts are shared per chat and use `(chat_id, base_currency, desired_currency)` as their composite identity. The chat LLM tools pass the request-scoped invoking user and chat into `CurrencyAlertService`, but the service currently checks only that a target chat exists and that the background agent is not creating an alert. Any member can therefore create or replace the shared alert for a currency pair, and any member can delete it.

The project already has a platform-aware authorization boundary. `AuthorizationService.validate_chat_admin` synchronizes the invoking user's current chat membership and accepts owners or administrators. Telegram group roles are resolved through the Bot API, while the owner of a supported private chat is treated as its administrator. WhatsApp currently supports private chats only.

## Goals / Non-Goals

**Goals:**

- Restrict price-alert creation, reconfiguration, and removal to current chat administrators.
- Keep private-chat price alerts manageable by the private-chat owner.
- Keep active-alert listing available to chat members.
- Enforce authorization before exchange-rate fetching or persistence mutation.
- Reuse the existing chat-administration semantics and structured authorization error.

**Non-Goals:**

- Changing price-alert persistence, ownership, composite identity, triggering, delivery, or cleanup.
- Adding WhatsApp group support or a new platform-role model.
- Hiding price-alert tools from the LLM based on role.
- Restricting active-alert listing to administrators.

## Decisions

### Enforce mutation authorization in `CurrencyAlertService`

Both `create_alert` and `delete_alert` will validate the invoking user as an administrator of the target chat before performing operation-specific external calls or repository writes. Existing target-chat and background-agent guards remain intact.

The service boundary protects every caller, including future callers that do not use the current LLM tool wrappers. Performing the check only in `set_up_currency_price_alert` and `remove_currency_price_alerts` was rejected because direct service calls could bypass it.

### Reuse live `validate_chat_admin` authorization

The service will delegate to `AuthorizationService.validate_chat_admin` with the request-scoped invoker and validated target chat. This preserves the established definitions of administrator and private-chat owner, refreshes platform membership at the protected operation, and returns the existing `NOT_CHAT_ADMIN` authorization error for ordinary members.

Reading the persisted membership directly was considered, since message ingestion already synchronizes it. It was rejected for the authorization decision because it couples correctness to a particular entry path and can use stale role state. The live check adds a platform lookup for protected operations but fails closed when current administrator status cannot be established.

### Treat every setup call as an administrator mutation

The repository saves by composite identity and replaces an existing alert when the same chat and currency pair already exists. Authorization will therefore cover both first creation and reconfiguration through the same `create_alert` path. No separate insert-versus-update permission is introduced.

### Leave read and background behavior unchanged

`get_active_alerts` remains available through the current member-scoped chat flow. Scheduled alert evaluation, price refresh, notification delivery, stale cleanup, and profile ownership reassignment do not represent interactive alert management and will not receive administrator checks.

## Risks / Trade-offs

- [A live Telegram role lookup adds latency and may duplicate the membership sync performed during message ingestion] → Limit the additional lookup to mutating operations, where current authorization is more important than avoiding one platform request.
- [A transient platform lookup failure can deny an administrator] → Preserve fail-closed authorization and return the existing structured authorization error without fetching a rate or mutating an alert.
- [Non-administrators still see management tools in the LLM tool catalog] → Rely on service-side enforcement as the security boundary; tool visibility can be reconsidered separately as a prompt and UX concern.

## Migration Plan

No data or schema migration is required. Deploy the service authorization checks and focused tests together. Rollback consists of reverting those checks; existing price-alert data remains compatible.

## Open Questions

None.
