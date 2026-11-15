# Proposal

## Why

Every client of the agent today is a chat platform that signs its own webhooks, so a developer's own machine has no way to reach their agent account. A command-line client (`abot`, built in the sibling `agent-cli` repository) must authenticate as an existing user and push notifications into that user's chats, and the web settings must be able to cut that access off again. The existing connect key and JWT machinery can carry this without a new profile type, a device table, or a new chat platform.

## What Changes

- Add one non-null `cli_token_generation` integer (default 0) to the users table (`UserDB`, table `simulants`) and carry it through the `User` domain object and mapper. The Alembic migration is generated and applied by the user.
- Add `POST /cli/connect` (unauthenticated): redeems a connect key for a CLI-scoped JWT. The server alone parses `ttl_as_text` (single-unit grammar, calendar-precise months and years, 6-month default, 2-year cap), validates device info, rotates the connect key atomically with token issuance, sends a best-effort "new CLI connected" alert (a system announcement, billed like other announcements) to the owner's best private chat, and returns the owner's `credit_balance` after that charge. Connect is not gated by EULA or waitlist state.
- Separate token scopes in `api/auth.py`: web routes reject any token that carries a `scope` claim; a new CLI dependency accepts only `scope: cli` tokens (signature, expiry, required claims, no database). The CLI controller adds the database check `cli_generation == user.cli_token_generation`.
- Add revoke-all through two doors, both `DELETE` requests on the owner's CLI devices: `DELETE /cli/user/{user_id_hex}/devices` (CLI token) and `DELETE /user/{user_id_hex}/cli/devices` (web token). Both increment the user's generation, which invalidates every CLI token at once.
- Add `GET /cli/chats` (chats the owner administers) and `POST /cli/notify/user/{user_id_hex}` / `POST /cli/notify/chat/{chat_id}`: plain-text notifications that respect the EULA and waitlist rules, with platform targeting, an anti-impersonation prefix for non-private chats, tail truncation with an ellipsis, normal delivery billing, one error for platform delivery failures, and the owner's `credit_balance` after charging in the response.
- Add new error codes and a `BadRequestError` (HTTP 400) used for TTL validation, matching the shared client contract. All other new validation errors stay 422.
- Update `docs/open-api-docs.yaml` for all new routes and the CLI token scheme, and fix the stale JWT `platform` enum.
- Deliver as six reviewable milestones (DB, domain, services, controllers, `main.py` wiring, docs), each ending with a user review stop. The `agent-cli` and `agent-web` implementations are separate changes in their own repositories; this change provides the contract they consume.

## Capabilities

### New Capabilities

- `cli-connect`: Redeeming a connect key for a CLI token, including lifetime grammar, calendar months, default and maximum lifetime, device validation, key rotation, the new-device alert, and balance reporting. Connect is not gated by onboarding state.
- `cli-token-scope`: Strict separation between web and CLI tokens, and per-request verification of a CLI token against its owner's current state.
- `cli-access-revocation`: Revoking every CLI token of a user at once, from the CLI or from the web settings.
- `cli-chat-listing`: Listing the chats a CLI user can notify.
- `cli-notifications`: Sending plain-text notifications to the user's own private chats or to administered chats, with the onboarding gate, targeting, prefixing, tail truncation, billing, balance reporting, and error mapping.

### Modified Capabilities

None. No existing base capability specifications are present.

## Impact

- **Database**: one additive column on `simulants`; one Alembic migration (user-generated); no new tables.
- **Backend code**: `src/db/model/user.py`, `src/features/users/{user,user_mapper}.py`, `src/api/auth.py`, `src/api/authorization_service.py` (reused, unchanged), `src/api/profile_connect_controller.py`, `src/features/integrations/integrations.py` (one helper made public), `src/util/{errors,error_codes}.py`, `src/di/di.py`, `src/main.py`; new `src/features/connect/connect_key_resolver.py`, `src/features/cli/*`, `src/api/cli_controller.py`, six `src/api/model/cli_*` models and one mapper.
- **Tests**: existing modules extended; new modules `test/features/connect/test_connect_key_resolver.py`, `test/features/cli/test_cli_access_service.py`, `test_cli_notify_service.py`, and `test/api/test_cli_controller.py`.
- **Public API**: six new routes and one new bearer scheme (`docs/open-api-docs.yaml`); web routes now reject scope-carrying tokens (no behavior change for existing web tokens).
- **Dependencies**: none added (`python-dateutil` and `httpx` are already dependencies).
- **Sibling work**: `agent-cli` consumes every `/cli/*` route; `agent-web`'s Command Line page consumes `DELETE /user/{user_id_hex}/cli/devices` and mirrors the new error codes for translations.
