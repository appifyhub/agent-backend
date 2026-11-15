# Design

## Context

See `proposal.md` for motivation. The relevant current state:

- **Request flow.** `src/main.py` route functions verify a JWT with `verify_web_jwt_credentials`, read the subject with `get_user_id_from_jwt`, build `DI(db, invoker_id_hex)` (`src/di/di.py`), and delegate to a controller in `src/api/` that calls services and repositories. Failures are `ServiceError` subclasses (`src/util/errors.py`) with codes from `src/util/error_codes.py`, rendered by `service_error_handler` as `{error_code, message, emoji}`. A test (`test/util/test_error_codes.py`) enforces that new codes take the next free number in their category.
- **Tokens.** `create_jwt_token` (`src/api/auth.py`) signs HS256 with `config.jwt_secret_key` and adds `exp`, `iat`, and `version`. Web tokens are minted by `SettingsController.__create_jwt_token` (claims `iss`, `sub`, `platform`, `platform_id`, `platform_handle`, 30 minutes by `config.jwt_expires_in_minutes`). Public attachment tokens reuse the same secret and are decoded by `verify_jwt_token` with their own required claims. `verify_web_jwt_credentials` returns raw claims and raises `HTTPException(401)` with a `{detail}` body.
- **Connect keys.** `UserDB.connect_key` is unique and indexed. `generate_connect_key()` (`src/features/users/user.py`) draws 12 characters from a 32-character alphabet (60 bits). `ProfileConnectService.connect_profiles` merges the newer profile (casualty) into the older one (survivor) and rotates the survivor's key through `regenerate_connect_key`; `__merge_user_data` starts from `replace(survivor)`. `ProfileConnectController.connect_profiles` normalizes keys with `strip().upper()`.
- **Authorization.** `AuthorizationService` (`src/api/authorization_service.py`) provides `validate_user` (404 `USER_NOT_FOUND` or 422 `MALFORMED_USER_ID`), `authorize_for_user` (403 `NOT_TARGET_USER`), `validate_chat_admin` (syncs the membership, 403 `NOT_CHAT_MEMBER` / `NOT_CHAT_ADMIN`), `get_authorized_chats` (scans up to `config.max_users * 10` chats and asks the platform for the user's rights in each, logging per-chat failures), and `require_user_is_chat_ready` (403 `WAITLIST_INVITED_POLICIES_REQUIRED` or `WAITLIST_ACCOUNT_NOT_ACTIVE`). `DI.invoker` wraps any validation failure in a 500 `InternalError(DI_DEPENDENCY_NOT_MET)`.
- **Outbound messages.** `PlatformBotSDK.send_text_message` (`src/features/integrations/platform_bot_sdk.py`) needs a DI whose invoker chat matches the target chat. The Telegram and WhatsApp SDKs (`src/features/chat/telegram/sdk/telegram_bot_sdk.py`, `src/features/chat/whatsapp/sdk/whatsapp_bot_sdk.py`) store the sent message as agent-authored and then charge `self.__di.invoker.id` through `SpendingService.charge_for_message_delivery` (`src/features/accounting/spending/spending_service.py`), after the provider accepted the message. `SpendingService.validate_message_delivery_pre_flight(chat, payer_id)` requires credits for one message to every non-agent member. `resolve_best_notification_chat` (`src/features/integrations/integrations.py`) picks Telegram, or WhatsApp when the user wrote there within 24 hours. The provider APIs (`telegram_bot_api.py` and `whatsapp_bot_api.py`, beside the SDKs) log and re-raise `requests.HTTPError` through `raise_for_status`. SDK methods never check affordability themselves; owner-level code that sends standalone messages (for example `CreditTransferService.__try_to_send_notification` in `src/features/accounting/transfers/credit_transfer_service.py`) runs `validate_message_delivery_pre_flight`, then `rollback_db_session`, then sends through `di.clone(invoker_chat_id = ...)`.
- **Limits.** `TEXT_MESSAGE_LIMITS` (`src/features/integrations/integration_config.py`) is 4096 for Telegram and WhatsApp; `measure_text_message_length` measures Telegram text by rendered length (`calculate_rendered_length`), WhatsApp by `len`.
- **Testing.** `di_for_tests()` provides real repositories on SQLite plus fakes for both bot APIs, the chat model, and the HTTP client, and installs its interceptor in a context variable that asyncio tasks and anyio worker threads inherit. There are no route-level tests for `main.py` yet.

## Goals / Non-Goals

**Goals:**

- Attach CLI access directly to the owner of a connect key, with scoped, expiring, individually stateless tokens that die together when the owner revokes.
- Keep every decision a client depends on explicit: lifetime grammar, exact (status, error code) pairs, claim set, response fields, and which routes accept which tokens.
- Reuse the existing authorization, onboarding, notification, and billing paths so CLI messages cost and behave like other agent messages and never bypass the EULA or the waitlist.
- Land as six reviewable milestones, bottom to top, each stopped for user review.

**Non-Goals:**

- CLI chat, streaming, a `cli` chat type, a device table, per-device listing or revocation, refresh tokens, or token introspection endpoints.
- Attachments, formatting options, scheduling, or idempotency keys for notifications.
- Gating connect, chat listing, or revoke-all on EULA or waitlist state (see D14).
- Implementing `agent-cli` or `agent-web`, or bumping the application version.

## Decisions

### D1. Stateless JWT plus one per-user revocation counter

Tokens are ordinary signed JWTs. Revocation is one integer, `UserDB.cli_token_generation` (not null, default 0), copied into every token at issue time and compared on every request. "Revoke all" increments it, so every older token dies immediately with no clock, list, or cleanup.

Alternatives rejected: a device table (explicitly out of scope; adds listing, cleanup, and sync), a `jti` deny-list (storage plus cleanup for a feature that only needs revoke-all), short tokens with refresh (a second flow, and the CLI would have to store two secrets), expiry-only (no emergency stop).

The per-request cost is one user read, which every CLI route needs anyway to authorize the owner.

### D2. Scope separation lives in `auth.py`, deny-by-default for web

- `verify_web_jwt_credentials` rejects any token that carries a `scope` claim, with the existing 401 response. This is a superset of the required "reject `scope == cli`", so a future scope is also denied on web routes by default. Existing web tokens and attachment tokens have no `scope` claim and are unaffected.
- `verify_cli_jwt_credentials` returns a frozen `CliTokenClaims` dataclass (same pattern as `PublicAttachmentTokenClaims`): `user_id`, `generation`, `device_id`, `hostname`, `os`. It accepts only signature-valid, unexpired tokens with `scope == "cli"`, a non-empty string subject, and an integer (not boolean) generation, and it raises `AuthenticationError(..., INVALID_CLI_TOKEN)` for everything else, so CLI clients always receive `{error_code, message, emoji}`. Web 401s keep their existing `{detail}` body.
- `create_cli_jwt_token` wraps `create_jwt_token` with claims `iss` (= `config.agent_bot_name`, the value `THE_AGENT.full_name` carries), `sub`, `scope`, `cli_generation`, `device_id`, `hostname`, `os`. `exp`, `iat`, and `version` come from `create_jwt_token`.
- Both token types share the HS256 secret, so the claim checks are the only separation. Every authenticated route MUST use one of the two dependencies; nothing may call `verify_jwt_token` directly except `verify_public_attachment_token`, which already requires claims that CLI tokens do not have.

### D3. The generation check lives in the controller, not in `auth.py`

`auth.py` stays database-free (signature, expiry, scope, claim shape). `CliController.require_valid_cli_token(claims)` is the single database check, and every CLI route calls it right after building its DI and before any controller action:

1. `authorization_service.validate_user(claims.user_id)`. A merged-away owner therefore fails with 404 `USER_NOT_FOUND`, as accepted. Reading `di.invoker` first would instead produce a 500 `DI_DEPENDENCY_NOT_MET`.
2. Compare `claims.generation` with `user.cli_token_generation`; mismatch raises 401 `CLI_ACCESS_REVOKED`.
3. The route has already built `DI(db, claims.user_id)`, so `di.invoker` is that same user and the other controller methods, which take no claims, read it lazily after this check passes. The controller does not inject anything.

User-scoped routes then call `authorize_for_user(invoker, path_user_id)` (403 `NOT_TARGET_USER`).

### D4. The lifetime parser is private to CliAccessService

`CliAccessService` resolves the requested lifetime in the private methods `__resolve_expiry(ttl_as_text, now)` and `__resolve_delta`, nothing else uses it. The module constants `DEFAULT_CLI_TOKEN_TTL` (6 months) and `MAX_CLI_TOKEN_TTL` (2 years), and the grammar pattern and hints, sit at the top of `cli_access_service.py` beside the code that owns them.

- **Grammar.** `^([1-9][0-9]*)(s|min|m|h|d|mo|M|y)$` over ASCII digits only (explicit `[0-9]`, never `\d`, which matches other scripts' digits). Case-sensitive, no trimming. `None` means the default; a blank string is invalid.
- **Arithmetic.** `timedelta` for `s`, `m`, `min`, `h`, `d` (a day is 24 hours). `dateutil.relativedelta` for `M`, `mo`, `y` (clamps to the last day of a short month). `python-dateutil` is already a dependency and `relativedelta` is already used in `search_source_formatter.py`.
- **Cap.** The requested expiry is compared with `now + relativedelta(years = 2)` as instants, so `731d` is valid exactly when the next two years contain a leap day.
- **Overflow.** Digit strings longer than nine digits (at least 10^9, over 31 years even in seconds) and any `OverflowError` or `ValueError` from date arithmetic are treated as too long, never as a server error.
- **Errors.** `BadRequestError(INVALID_CLI_TTL)` and `BadRequestError(CLI_TTL_TOO_LONG)` with messages that state the grammar and the maximum.
- `connect` reads the clock once (`datetime.now(timezone.utc)`, truncated to whole seconds) and passes it to `__resolve_expiry`; the service tests pin calendar cases by replacing `datetime` in the `cli_access_service` module with a fixed-clock subclass, the only patch they use.
- No new `Config` setting is introduced (`src/util/config.py` and `test/util/test_config.py` stay untouched): the defaults are fixed by the contract and live beside the code that owns them.

### D5. HTTP 400 through a new `BadRequestError`

The shared client contract fixes 400 for both TTL errors, and the CLI classifies errors by (status, code). The repository has only 422 `ValidationError`, so `util/errors.py` gains `BadRequestError` (HTTP 400, same emoji as `ValidationError`). Only the two TTL codes use it. Every other new validation error stays 422 through `ValidationError`, as does `INSUFFICIENT_CREDITS` (existing 422 / 1034).

### D6. Connect resolves the owner first, then locks, rotates, issues, and commits

`POST /cli/connect` is unauthenticated, and its credential is the connect key. Like `get_user_id_from_jwt` for web routes, the key is resolved before the real DI exists:

- `require_user_by_connect_key(connect_key, db) -> User` in `src/features/connect/connect_key_resolver.py` normalizes the key with `strip().upper()` (the same normalization `ProfileConnectController.connect_profiles` applies), reads the user with `DI(db).user_repo.get_by_connect_key` (a plain unlocked read), and raises `NotFoundError(CONNECT_KEY_NOT_FOUND)` for no match. It never echoes the key. The name follows the repository's `require_*` convention for lookups that raise.
- The route calls it with the request session, builds `DI(db, owner.id.hex)`, and calls `di.inject_invoker(owner)` with the resolved user itself, not only its id. That injected snapshot is the credential that was presented, and step 2 depends on it.

`CliAccessService.connect(ttl_as_text, device_id, hostname, os)` then runs on that DI and never resolves the key a second time:

1. Resolve the expiry (pure; fails with 400 before any database write) and validate device information (D7).
2. `user_repo.update_locked(di.invoker.id, rotate, commit = False)` takes the row lock; `rotate` re-checks `locked.connect_key == di.invoker.connect_key` and returns `replace(locked, connect_key = generate_connect_key())`. The check is a compare-and-swap between the unlocked read and the lock: connect consumes the key, so a concurrent request that rotated it first makes the loser fail with the same 404.
3. Create the JWT from the locked row's `cli_token_generation`.
4. `db.commit()`. Rotation is durable only together with a token that exists; any exception calls `db.rollback()` and re-raises (the pattern `ProfileConnectService.connect_profiles` uses).
5. Send the alert (D8), re-read the owner, and return `Connection(token, expires_at, user)`.

If the route injected only the owner's id, the DI would load the invoker lazily after the resolution and the snapshot would already hold the rotated key, so a stale key could be redeemed twice. The injected resolved user is therefore part of the contract.

`ProfileConnectService.regenerate_connect_key` is not reused because it saves a stale snapshot without a lock; connect needs check-and-rotate atomicity. It reuses `generate_connect_key()`, so keys keep their shape and entropy. Connect performs no onboarding check (D14).

`expires_at` is computed once, truncated to whole seconds, and the token is issued with `expires_in = expires_at - now`, so the token's `exp` matches `expires_at` to within one second (`create_jwt_token` takes its own clock reading). The controller maps the result to `CliConnectResponse(token, expires_at, user_id = user.id.hex, user_display_name, credit_balance)`; `expires_at` is a timezone-aware UTC `datetime` serialized as RFC 3339 with `Z`. `credit_balance` comes from the owner re-read after the alert attempt, so it includes any alert charge. The display name is `full_name`, else the first handle from `resolve_any_external_handle`, else `user.id.hex`.

The controller and routes never log the key, the token, or the `Authorization` header (the existing merge route logs its key at debug level; this change does not copy that).

### D7. Device information is validated by the server

The hostname flows into signed claims, the alert text, and the group prefix, so the server does not trust the client's sanitizing. Constants live in `cli_access_service.py`: `device_id` may be any string that is not blank (it is only an opaque label in the signed claims, and a blank value would make a token the verifier refuses), `hostname` must match `^[A-Za-z0-9.-]{1,32}$`, `os` must match `^[A-Za-z0-9._/-]{1,32}$` (Go `GOOS` values pass). Violations raise `ValidationError(INVALID_CLI_DEVICE)` (422) before any state changes. Rejecting is preferred over rewriting: the CLI already sanitizes, so a rejection signals a client bug.

### D8. The new-device alert is a system announcement

A private method of `CliAccessService` runs after the commit, inside `try/except Exception` so it can never change the connect outcome. Like other system notices (for example the credit transfer notification), the alert goes through `SysAnnouncementsService`, which rewrites the raw information in the agent's voice and the chat's language.

1. The invoker is already the redeemed owner (the route injected it, D6), so `resolve_best_notification_chat(owner, di)` runs on the service's own DI; none means skip quietly.
2. `di.spending_service.validate_message_delivery_pre_flight(chat, owner.id)`, the stateless affordability check every standalone owner runs; `INSUFFICIENT_CREDITS` is logged as a warning and skips the alert instead of pushing the owner into overdraft.
3. `rollback_db_session()`, resolve the copywriting tool with `tool_choice_resolver.require_tool(SysAnnouncementsService.TOOL_TYPE, default_tool_for(...))`, and run `di.sys_announcements_service(raw_message, chat, tool).execute()`. An empty result raises `ExternalServiceError(ANNOUNCEMENT_NOT_RECEIVED)`, which is logged.
4. `rollback_db_session()`, then `di.clone(invoker_chat_id = chat.chat_id.hex).platform_bot_sdk().send_text_message(str(chat.external_id), announcement)`, so the invoker chat type matches the target chat.

The raw information is formatted in place: a new command line client connected, its hostname and operating system, the expiry in UTC as `YYYY-MM-DD HH:MM`, and that the user should open the agent's settings and revoke all CLI access if it was not them. It names no menu path, so UI renames cannot make it wrong. The owner pays for the copywriting call and, after the platform accepts the message, for the delivery (Telegram free, WhatsApp at its configured price).

### D9. Revocation is one service method behind two routes

`CliAccessService.revoke_all()` runs `user_repo.update_locked(di.invoker.id, lambda u: replace(u, cli_token_generation = u.cli_token_generation + 1))`, a row-locked read-modify-write so concurrent calls each count. Two entry points call it, each with the authenticated owner already injected as the invoker:

- `CliController.revoke_all(user_id_hex)` is the one revoke method, used by both routes, which are `DELETE` requests on the owner's CLI devices (revoking all CLI access removes all devices; a later device listing will use the same noun with `GET`): `DELETE /cli/user/{user_id_hex}/devices` (the route runs `require_valid_cli_token` first, D3) and `DELETE /user/{user_id_hex}/cli/devices` (a web token, so the invoker comes from the DI as for other web routes). It authorizes with `authorize_for_user(di.invoker, user_id_hex)`. The method lives in the CLI controller because it concerns CLI access, not profile connection.

Both routes return `{"status": "OK"}`. No response ever includes the generation. A profile merge keeps the higher of the two generations (`max` in `__merge_user_data`), so a token revoked before the merge never becomes valid again; a survivor's tokens stay valid unless the casualty's generation was higher. A test pins it.

### D10. Chat listing is a thin controller method

`CliController.list_chats()` calls `authorization_service.get_authorized_chats(di.invoker)` and maps each `ChatConfig` with a new `cli_chat_api_mapper.domain_to_api` into `CliChatResponse(chat_id = chat.chat_id.hex, platform = chat.chat_type.value, title, is_private)`. Ordering comes from `get_authorized_chats` (private first, then platform, case-insensitive title, external id, chat id). Per-chat platform failures are already swallowed there, which satisfies the tolerance requirement. No membership refresh happens (unlike the web `GET /settings/chats`).

### D11. Notifications: one pipeline, three ways to pick the chat

`CliNotifyService` exposes `notify_invoker(hostname, message, platform)` and `notify_chat(hostname, chat_id, message)`. The owner is always `di.invoker` (the route builds the DI from the token's user id, D3), so neither method takes a user. Both return a nested frozen `Delivery(chat, user)` and end in one private pipeline:

1. **Check onboarding** (D14): `authorization_service.require_user_is_chat_ready(user)`, before anything else.
2. **Validate the message**: strip, then 1 to `min(TEXT_MESSAGE_LIMITS.values())` characters (currently 4096) or `ValidationError(INVALID_NOTIFICATION_MESSAGE)`.
3. **Resolve the chat**:
   - Explicit platform (validated here with `ChatType.lookup` against `CLI_NOTIFICATION_PLATFORMS` in `integration_config.py`, telegram and whatsapp, else `ValidationError(INVALID_PLATFORM)`, so the onboarding gate always comes first): `find_private_chat(user, chat_type, di)`; none raises `AuthorizationError(NO_PRIVATE_CHAT)`. No 24-hour heuristic here: the provider is authoritative, and the heuristic only looks at the last 30 messages.
   - No platform: `resolve_best_notification_chat`; none raises `AuthorizationError(NO_PRIVATE_CHAT)`, including when the only private chat is a WhatsApp chat outside the 24-hour window.
   - Chat id: `authorization_service.validate_chat_admin(user, chat_id)` (existing 404/422/403 behavior).
   `_find_private_chat` in `integrations.py` is renamed `find_private_chat` (it is already used for exactly this lookup by `resolve_best_notification_chat`; no behavior change).
4. **Compose the text**: apply the prefix (D12), then truncate the tail if the result is too long (D13).
5. **Pre-flight and send**: `validate_message_delivery_pre_flight(chat, user.id)`, `rollback_db_session()`, then `di.clone(invoker_chat_id = chat.chat_id.hex).platform_bot_sdk().send_text_message(str(chat.external_id), text)`. The SDK stores the message and charges the invoker only after the provider accepted it, so rejected sends are neither stored nor charged.
6. **Fail simply on provider errors**: catch `requests.RequestException` around the send and raise `ExternalServiceError(NOTIFICATION_DELIVERY_FAILED)` (502) from it. Provider-specific signals (blocked bot, WhatsApp 24-hour window, throttling) are not interpreted, like every other provider call in the repository. `ServiceError`s raised inside the SDK path (for example `UNSUPPORTED_CHAT_TYPE`) propagate unchanged.
7. **Report the balance**: re-read the owner after the send; `Delivery.user` is that re-read owner, so its `credit_balance` includes this delivery's charge.

Notifications are stored as agent-authored messages, so a later agent reply in that chat sees them in its history; the prefix labels their origin in groups.

### D12. Anti-impersonation prefix

Every notification starts with `🖥️ `, so it is recognizable as coming from a command-line client. A message to a non-private chat continues with `[<identity>@<hostname>] `. The identity comes from the invoking user object loaded from the token's subject, never from the request: `resolve_external_handle(invoker, chat.chat_type)` (the Telegram username or the WhatsApp phone number), otherwise `resolve_external_id(invoker, chat.chat_type)` (the numeric Telegram user id or the WhatsApp user id). There is no platform label: everyone reading the message already knows which platform they are on. The hostname is the signed `hostname` claim. Private chats get only the `🖥️ ` (no identity or hostname, since the reader is the owner).

### D13. Tail truncation with an ellipsis

When `measure_text_message_length(text, chat.chat_type)` exceeds `resolve_text_message_limit(chat.chat_type)`, the end of the message is cut, an ellipsis (`…`) is appended, and the prefix is always kept whole, so the final text is never longer than the limit (4096 today). The implementation binary-searches the longest message head such that prefix + right-stripped head + `…` still fits, using the same measure and search style as `_split_for_provider_limit` in `domain_langchain_mapper.py`. A message that already fits is delivered untouched, with no ellipsis. The prefix is at most about 75 characters, so a cut message is never empty. Private chats get the short `🖥️ ` prefix, so a 4096-character message is cut there too.

### D14. EULA and waitlist gating

Connect is not gated: connect keys are only shown in the web app after onboarding, so redeeming one needs no readiness check. Chat listing and revoke-all are not gated either, so a user can always see their chats and cut CLI access off. Both notification routes call `authorization_service.require_user_is_chat_ready(user)` (`src/api/authorization_service.py`) before anything else, so a CLI can never bypass the EULA or the waitlist. It raises 403 `WAITLIST_INVITED_POLICIES_REQUIRED` (3008) for an owner who has not accepted the policies and is either invited to start or off the waitlist, and 403 `WAITLIST_ACCOUNT_NOT_ACTIVE` (3007) for any other waitlisted owner. Both codes already exist, so no code is added. They are usage states and not token problems, so the CLI keeps its token on them.

### D15. User-facing copy lives in the owning file

The repository has no central user-facing copy module: service messages are inline strings (for example in `credit_transfer_service.py`), and `prompt_library.py` holds model prompts, not notices. So the CLI services keep their copy inline too: the notification prefix and the ellipsis in `cli_notify_service.py`, and the new-device alert information in `cli_access_service.py` (the announcement service rewrites it). Shared platform facts live in `integration_config.py`. Error messages stay inline, as everywhere else.

### D16. Error contract (agreed with `agent-cli`)

The CLI classifies by (HTTP status, error code) and prints its own text per code. Numbers are the next free ones in each category at the time of writing and must still follow the next-number rule when implemented.

New error codes (the web change mirrors this table for translations; the onboarding codes 3007 and 3008 already exist):

| Code | Number | HTTP |
|---|---|---|
| `INVALID_CLI_TTL` | 1043 | 400 |
| `CLI_TTL_TOO_LONG` | 1044 | 400 |
| `INVALID_CLI_DEVICE` | 1045 | 422 |
| `INVALID_NOTIFICATION_MESSAGE` | 1046 | 422 |
| `CONNECT_KEY_NOT_FOUND` | 2015 | 404 |
| `INVALID_CLI_TOKEN` | 4004 | 401 |
| `CLI_ACCESS_REVOKED` | 4005 | 401 |
| `NOTIFICATION_DELIVERY_FAILED` | 5018 | 502 |

Situations, including existing codes:

| Situation | Status | Code (number) |
|---|---|---|
| Bad lifetime syntax | 400 | `INVALID_CLI_TTL` (1043) |
| Lifetime over two years | 400 | `CLI_TTL_TOO_LONG` (1044) |
| Bad device id, hostname, or os | 422 | `INVALID_CLI_DEVICE` (1045) |
| Empty or oversized notification | 422 | `INVALID_NOTIFICATION_MESSAGE` (1046) |
| Unsupported platform | 422 | `INVALID_PLATFORM` (1019, existing) |
| Insufficient credits | 422 | `INSUFFICIENT_CREDITS` (1034, existing) |
| Malformed user or chat id | 422 | `MALFORMED_USER_ID` (1029) / `MALFORMED_CHAT_ID` (1030), existing |
| Unknown or used connect key | 404 | `CONNECT_KEY_NOT_FOUND` (2015) |
| Unknown chat / merged-away owner | 404 | `CHAT_NOT_FOUND` (2002) / `USER_NOT_FOUND` (2001), existing |
| Owner not onboarded: policies not accepted | 403 | `WAITLIST_INVITED_POLICIES_REQUIRED` (3008, existing) |
| Owner not onboarded: waitlisted | 403 | `WAITLIST_ACCOUNT_NOT_ACTIVE` (3007, existing) |
| Not chat admin / not chat member | 403 | `NOT_CHAT_ADMIN` (3001) / `NOT_CHAT_MEMBER` (3009), existing |
| Path user is not the token owner | 403 | `NOT_TARGET_USER` (3002, existing) |
| No private chat on the platform | 403 | `NO_PRIVATE_CHAT` (3004, existing) |
| Bad signature, expiry, scope, or claims | 401 | `INVALID_CLI_TOKEN` (4004) |
| Generation mismatch (revoked) | 401 | `CLI_ACCESS_REVOKED` (4005) |
| Other provider failure | 502 | `NOTIFICATION_DELIVERY_FAILED` (5018) |

Token problems are always 401 and never 403, so the CLI may delete its token on 401. A 403 can be a normal usage error or onboarding state (wrong `--chat`, owner not onboarded), so the CLI keeps its token for `NOT_CHAT_ADMIN`, `NO_PRIVATE_CHAT`, `NOT_CHAT_MEMBER`, `WAITLIST_INVITED_POLICIES_REQUIRED`, and `WAITLIST_ACCOUNT_NOT_ACTIVE`.

### D17. Validation in services, not in Pydantic constraints

Payload models declare only types. Semantic checks (device information, message length, platform) raise `ValidationError` with codes so clients get `{error_code, message, emoji}`. Missing fields and wrong types still produce FastAPI's default 422 `{detail}` body, exactly as every other endpoint does.

### D18. Documentation

`docs/open-api-docs.yaml` gains the six routes (tag `CLI` for the CLI routes, tag `Profile Connection` for the web revoke route), schemas for every payload and response (including `credit_balance` on the connect and notify responses), a `cliBearerAuth` security scheme, reusable `BadRequestError` (400) response, and a `CliJWTPayload` schema (`sub`, `scope`, `cli_generation`, `device_id`, `hostname`, `os`, `iss`, `exp`, `iat`, `version`). The notify routes also document the two 403 onboarding responses.

Decision on the stale JWT `platform` enum: `JWTPayload.platform` (currently `[telegram, whatsapp]`) is aligned with all `ChatConfigDB.ChatType` values (`telegram`, `whatsapp`, `github`, `background`), because `__create_jwt_token` writes `chat_type.value` into the claim. Other `[telegram, whatsapp]` enums in the document (for example chat settings) stay as they are. The application version is not bumped here; `tools/bump_version` owns that at release time.

### D19. Testing follows `AGENTS.md`

Real DI, SQLite repositories, shared stubs and fakes, no mocks of owned code, assertions through public APIs. Needed additions: `cli_token_generation` defaults in `stubs.db.user_db` and `stubs.domain.user`; CLI claim, payload, and response stubs in `stubs/api.py`; a provider-error stub in `stubs/external.py` (a `requests.HTTPError` carrying a status and JSON body); and `delivery_errors` on `FakeWhatsAppBotAPI`, mirroring the existing `FakeTelegramBotAPI.delivery_errors`.

Existing modules are extended where the production subject exists (`test_auth.py`, `test_user_mapper.py`, `test_user_repo.py`, `test_profile_connect_service.py`, `test_profile_connect_controller.py`, `test_authorization_service.py`, `test_integrations.py`, `test_errors.py`). The new test modules are part of this plan: `test/features/connect/test_connect_key_resolver.py`, `test/features/cli/test_cli_access_service.py` (including the lifetime scenarios), `test/features/cli/test_cli_notify_service.py`, and `test/api/test_cli_controller.py`. `main.py` has no tests in this repository, so the routes are thin wiring only and are verified by listing them.

### D20. Layout and milestone order

New: `src/features/connect/connect_key_resolver.py`, `src/features/cli/{cli_access_service,cli_notify_service}.py`, `src/api/cli_controller.py`, `src/api/mapper/cli_chat_api_mapper.py`, `src/api/model/{cli_connect_payload,cli_connect_response,cli_chat_response,cli_notify_user_payload,cli_notify_chat_payload,cli_notify_response}.py`. DI gains `cli_access_service`, `cli_notify_service`, and `cli_controller` providers following the existing lazy-import pattern. Milestones run bottom to top as listed in `tasks.md`; each ends with a stop for user review, and nothing from the next milestone starts before approval.

## Risks / Trade-offs

- **Shared signing secret between token types** → Isolation depends on claim checks (D2). Mitigate with deny-by-default on web, allow-only on CLI, and tests for every token type on both route families.
- **Long-lived bearer tokens (up to two years)** → Default is six months, the CLI stores tokens in the OS keychain by default, and revoke-all works from both the CLI and the web. A leaked unused connect key stays valid until regenerated, the same exposure the merge flow has; the 60-bit key makes guessing impractical.
- **Revocation is all-or-nothing** → Accepted for v1 (no device table). Users see only "Revoke all CLI access".
- **Lost update on the counter** → Generic `UserRepository.save` writes every column from a snapshot, so a save that loaded the user before a revoke and writes after it could restore the old generation. All such saves are short, same-user flows; revoke itself is row-locked. If this ever matters, exclude the column from `apply_to_db_model` and increment atomically.
- **Alert is best-effort and AI-written** → An owner with no eligible chat, with insufficient credits, or whose platform or copywriting call fails gets no alert; the connect still succeeds. The wording is the announcement model's, so only its facts (device, expiry, revoke from settings) are pinned.
- **Identity in group prefixes** → The prefix shows the owner's handle on the chat's own platform (a Telegram username in a Telegram group), so group members see only an identity they already know there. The numeric platform id is the fallback.
- **Balance is a snapshot** → `credit_balance` is read right after the charge; concurrent spending can change it before the client shows it. It is informational, so no lock is taken.
- **`get_authorized_chats` cost** → It scans all chats and calls Telegram per group, exactly like the web chat list. No caching is added; revisit if the listing becomes slow.
- **Best-chat heuristic window** → `resolve_best_notification_chat` looks at the latest 30 messages for the owner's last message. Notification messages are agent-authored, so more than 30 notifications without a reply can push the owner's message out and make a WhatsApp chat look stale. The explicit-platform path does not use the heuristic.
- **Provider failures are not interpreted** → Any `requests.RequestException` from the send becomes one 502 `NOTIFICATION_DELIVERY_FAILED`, like other provider calls in the repository. The CLI cannot tell a blocked bot or an expired WhatsApp window from an outage; this is accepted.
- **Notification text in the agent's history** → Group members see CLI messages as agent messages and the agent's context may include them; the prefix labels the origin and only chat administrators can send.
- **Merged-away tokens return 404** → Accepted; the CLI treats `USER_NOT_FOUND` as revoked and asks the user to reconnect.
- **`expires_at` and `exp` differ by up to a second** → Documented and tested with a one-second tolerance.

## Migration Plan

1. Milestone 1: add the column, then ask the user to run `./tools/db_generate_migration -y --name add_cli_token_generation` (the script requires `--name` together with `-y`) and review that the revision only adds `simulants.cli_token_generation` as a non-null integer with server default `0`, formatted like the existing revisions. Apply with `./tools/db_apply_migration` only after approval. Production start already runs `./tools/db_apply_migration -y`, so deploying the application applies the migration.
2. Deploy order: database (additive and defaulted, safe for old code), backend, then the web page and the CLI release.
3. Rollback: the column can stay (old code ignores it). To kill all CLI access without a deploy, run `UPDATE simulants SET cli_token_generation = cli_token_generation + 1`.
4. Post-deploy check on staging: a real connect, notify, and revoke-all round trip works.
