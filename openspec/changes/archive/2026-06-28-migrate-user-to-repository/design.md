## Context

`simulants` is the central user table. It still uses `UserSave`, `User`, and `UserCRUD`, while newer persistence areas use feature-level dataclasses, mappers, and repositories. User persistence is harder than the recent CRUD migrations because the same legacy `UserSave` type currently represents several different states:

```
complete user state
    settings writes, profile merges, internal agent users

remote platform snapshot
    Telegram / WhatsApp author data before DB resolution

locked mutable DB row
    credit deductions, purchases, transfers
```

Telegram and WhatsApp data resolvers already show the ambiguity. They receive a partial remote user snapshot, look up an existing row by platform identifiers, then manually copy back DB-owned fields such as secrets, tool choices, credits, onboarding flags, group, and connect key before saving.

The target shape follows the repository pattern used by chat configs, chat messages, sponsorships, price alerts, tools cache, usage records, and purchase records:

```
caller
  │
  ▼
repository ─────▶ UserDB
  │                  ▲
  ▼                  │
User domain ◀──── mapper
```

For remote platform users, the mapper pattern should mirror chat config:

```
UserRemoteData
    │
    ├─ no existing user ─▶ from_remote_data(...) + caller onboarding defaults ─▶ User
    │
    └─ existing user ────▶ apply_remote_data(existing, remote) ───────────────▶ User
```

The one intentional difference from chat config is that the repository should not own new-user onboarding defaults. Whether a new user is waitlisted depends on current capacity and caller context, so platform resolvers and sponsorship flows should compute those defaults before converting remote data to full user state.

## Goals / Non-Goals

**Goals:**

- Introduce a feature-level user domain dataclass, remote-data dataclass, mapper, and repository.
- Keep `UserDB` as the only SQLAlchemy model for the existing `simulants` table.
- Preserve current database schema, encryption behavior, generated UUIDs, generated connect keys, created-at behavior, platform lookups, settings writes, sponsorship user creation, accounting locks, profile connection, and API behavior.
- Make remote platform field ownership explicit and independently testable.
- Keep SQLAlchemy row mutation inside mappers/repositories except for documented transaction seams.
- Remove legacy `db/schema/user.py` and `db/crud/user.py` only after all production and test references are gone.

**Non-Goals:**

- No table, column, index, unique constraint, enum, encrypted column, default, or Alembic migration change.
- No user settings payload/response, JWT, sponsorship, purchase, transfer, waitlist, profile-connect, external-tool, prompt, or OpenAPI behavior change.
- No enum relocation for `UserDB.Group`.
- No redesign of profile-connection dependent-entity bulk migrations.
- No broader repository transaction policy change across all existing repositories.

## Decisions

### 1. Keep One SQLAlchemy Model

`UserDB` remains the only SQLAlchemy representation for `simulants`. The new feature model is a dataclass mapped to and from `UserDB`.

**Rationale**: The table already expresses the required persistence shape. A second SQLAlchemy model would duplicate metadata and increase Alembic risk.

**Alternative considered**: Create a parallel SQLAlchemy model. Rejected for the same reason as prior repository migrations: competing table ownership without functional benefit.

### 2. Use One Complete Domain Model with Nullable Create-Time ID Fields

The complete domain model should include all persisted fields:

```
User(
    id: UUID | None = None,
    created_at: date | None = None,
    connect_key: str = field(default_factory = generate_connect_key),
    ...
)
```

`id` and `created_at` can be absent only before the first save. The repository lets existing SQLAlchemy defaults generate them, refreshes the row, and returns a persisted domain snapshot with concrete values. Updates preserve `id` and `created_at`.

**Rationale**: This matches the current `UserSave` create lifecycle and the chat-config migration: the DB model already owns UUID generation, and callers receive the concrete ID after persistence.

**Alternative considered**: Require all callers to generate UUIDs before saving. Rejected because it changes current identity ownership during a migration.

### 3. Model Remote Platform Users Separately

Platform mappers should return `UserRemoteData`, not complete `User`:

```
UserRemoteData(
    full_name: str | None = None,
    telegram_username: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_user_id: int | None = None,
    whatsapp_user_id: str | None = None,
    whatsapp_phone_number: SecretStr | None = None,
)
```

Remote data has no internal ID, no connect key, no created-at, no secrets beyond the platform phone value, no credits, no group, and no onboarding flags.

**Rationale**: Telegram and WhatsApp author payloads are partial snapshots. Treating them as complete persistence objects is why the current resolvers must manually preserve most fields.

**Alternative considered**: Keep a single nullable `User` object for remote and complete states. Rejected because it preserves the same ambiguity as `UserSave`.

### 4. Keep Remote Merge Semantics in the Mapper

The mapper should expose:

- `from_remote_data(remote_data) -> User`
- `apply_remote_data(existing_user, remote_data) -> User`

For an existing user:

- Preserve `id`, `created_at`, `connect_key`, secrets, tool choices, credits, onboarding flags, and group.
- Fill `full_name` from remote data only when the existing full name is empty.
- Update non-null platform-owned identifiers/handles from the remote snapshot.
- Preserve existing platform fields when the remote snapshot omits them.

For a new user:

- Use platform fields from remote data.
- Leave onboarding flags at domain defaults until the caller applies explicit onboarding policy.
- Generate a connect key through the domain default.
- Leave user-owned settings, secrets, credits, and tool choices at domain defaults.

**Rationale**: These are platform snapshot semantics, not storage mechanics. Keeping the remote field mapping in the mapper mirrors chat config and makes ownership testable, while keeping onboarding policy at the caller avoids hiding capacity behavior in conversion code.

**Alternative considered**: Put remote merge behavior inside `UserRepository.save(UserRemoteData)`. Rejected because new-user onboarding defaults depend on capacity checks and should not make the repository depend on application configuration.

### 5. Repository Saves Complete Domain State and Queries Platform Identifiers

The repository should expose the current useful CRUD surface while returning domain snapshots:

- `get(user_id) -> User | None`
- `get_all(skip, limit) -> list[User]`
- `count() -> int`
- `get_by_telegram_user_id(telegram_user_id) -> User | None`
- `get_by_telegram_username(telegram_username) -> User | None`
- `get_by_whatsapp_user_id(whatsapp_user_id) -> User | None`
- `get_by_whatsapp_phone_number(whatsapp_phone_number) -> User | None`
- `get_by_connect_key(connect_key) -> User | None`
- `get_by_remote_data(remote_data) -> User | None`
- `save(user) -> User`
- `delete(user_id) -> User | None`

`save(User)` inserts complete state when `id` is absent or unknown, and applies complete mutable state to an existing row when `id` is found. Existing-row mutation must use `user_mapper.apply_to_db_model(domain_model, db_model)`.

**Rationale**: Matching the legacy lookup surface keeps migration focused on type boundaries. `get_by_remote_data` centralizes the Telegram/WhatsApp identifier lookup branch without hiding creation semantics.

**Alternative considered**: Keep public `create` and `update` methods. Rejected for production callers because current migrations have standardized on `save` for complete domain state.

### 6. Keep Secret Conversion at the Mapper Boundary

The domain model keeps secret-like values as `SecretStr | None`. `domain(db_model)` wraps decrypted DB strings in `SecretStr`, and `db(domain_model)` / `apply_to_db_model(...)` unwrap `SecretStr` to plain values before assigning them to `EncryptedString` columns.

**Rationale**: Domain callers should not handle encrypted-storage strings directly. This preserves current Pydantic behavior while removing dependency on `model_dump()` overrides.

**Alternative considered**: Store plain strings in the domain for simplicity. Rejected because it weakens the API currently provided by `db.schema.user.User`.

### 7. Preserve Locked Accounting Updates with Domain Callbacks

The repository should retain locked update operations, but callbacks should work with domain users rather than SQLAlchemy rows:

- `update_locked(user_id, update_fn: Callable[[User], User]) -> User`
- `update_locked_pair(first_id, second_id, update_fn: Callable[[User, User], tuple[User, User]]) -> tuple[User, User]`

The repository locks rows with `with_for_update()`, converts them to domain snapshots, applies the callback, maps the returned domain state back onto the locked rows, commits, refreshes, and returns domain snapshots.

**Rationale**: Spending, purchase allocation/deallocation, and transfers require row-level locks. Keeping locks in the repository preserves concurrency behavior while removing SQLAlchemy row mutation from services.

**Alternative considered**: Keep callback mutation over `UserDB` rows. Rejected because it keeps persistence types in accounting services.

### 8. Treat Profile Connection as a Transaction Seam

`ProfileConnectService` already performs a multi-table transaction: migrate dependent records, delete the casualty user, update the survivor, regenerate the connect key, and commit atomically. This migration should handle it in a late milestone and avoid using ordinary committing repository methods inside that transaction.

The preferred implementation is to keep the bulk dependent-entity updates direct and use `UserDB` plus `user_mapper.apply_to_db_model(...)` inside the service transaction, or add narrowly named non-committing repository helpers only if review shows that is clearer. Do not add broad commit flags to every repository method as a side effect of this migration.

**Rationale**: Existing repositories commit per operation. Profile connection needs a larger unit of work. Preserving that atomicity is more important than forcing every line through the repository immediately.

**Alternative considered**: Add `commit = False` to normal repository `save` and `delete`. Rejected as the default plan because it spreads transaction policy into a repository API used by ordinary callers.

### 9. Migrate in Reviewable Milestones

The safest order is:

1. Add domain, remote-data, mapper, repository, DI, SQL helper, and focused tests.
2. Migrate platform user mapping/resolution because it owns the remote merge ambiguity.
3. Migrate settings and authorization.
4. Migrate lookup helpers, sponsorships, integrations, prompt/chat/support paths.
5. Migrate accounting locked updates.
6. Migrate profile connection.
7. Remove legacy CRUD/schema only after reference searches are clean.

**Rationale**: User persistence touches almost every feature. Moving remote resolution first reduces the highest ambiguity, while locked accounting and profile connection stay protected until repository behavior is well covered.

## Risks / Trade-offs

- **Remote platform data overwrites user-owned fields** -> Test every DB-owned field preservation path for Telegram and WhatsApp existing users.
- **New-user onboarding defaults move to the wrong layer** -> Keep capacity checks in resolvers/services and pass explicit defaults into mapper conversion.
- **Secret values leak as plain strings** -> Keep `SecretStr` in the domain and test mapper unwrap/wrap behavior for every encrypted field.
- **Credit updates lose row-level locking** -> Preserve `with_for_update()` in repository locked methods and run spending, purchase, and transfer tests.
- **Profile connection loses transaction atomicity** -> Migrate it last and keep its multi-table operation inside one transaction.
- **Generated IDs, connect keys, or created-at values change** -> Let existing DB/domain defaults generate values and assert concrete refreshed values after save.
- **Large mock churn hides behavior regressions** -> Use focused repository tests first, then migrate production boundaries in review gates with existing tests as canaries.

## Migration Plan

1. Build user persistence foundation beside legacy CRUD/schema and keep both test sets green.
2. Migrate Telegram and WhatsApp remote user data flows to `UserRemoteData`, mapper conversion, and repository persistence.
3. Migrate authorization and settings user reads/writes to the new domain model.
4. Migrate integration helpers, sponsorship flows, external-token lookup, chat membership/support/prompt consumers, and API controllers.
5. Migrate accounting locked updates and verify credit-balance concurrency behavior.
6. Migrate profile connection without breaking its multi-table transaction.
7. Remove legacy DI access, CRUD/schema files, SQL helpers, and obsolete tests after reference searches are clean.
8. Run the full offline suite, all-files pre-commit, and strict OpenSpec validation.

Rollback remains straightforward before legacy deletion because the database schema is unchanged and the legacy CRUD can coexist with the repository during migration.

## Open Questions

None. The one scoped implementation decision is that profile connection remains a transaction seam and should not force broad repository commit flags unless review requires that trade-off.
