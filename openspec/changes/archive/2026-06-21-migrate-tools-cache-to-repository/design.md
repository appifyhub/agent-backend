## Context

`tools_cache` still uses the legacy `db/schema` + `db/crud` persistence pattern. `ToolsCacheCRUD` accepts `ToolsCacheSave`, returns `ToolsCacheDB`, and consumers convert rows with `ToolsCache.model_validate(...)`. The legacy schema also contains cache-entry behavior (`is_expired`) and uses `created_at: datetime = datetime.now()`, which evaluates once when the module is imported rather than when each entry is created.

The cache is shared infrastructure used by chat attachment processing, currency exchange-rate fetching, web fetching, HTML cleanup, Twitter fetching, and scheduled cleanup. Cache entries are internal full-state objects rather than partial external snapshots:

```
caller
  │
  ▼
repository ─────▶ ToolsCacheDB
  │                    ▲
  ▼                    │
domain dataclass ◀──── mapper
```

```
key
    required deterministic identity, never DB-generated

value
    required full replacement value

created_at
    required timestamp, defaulted per domain instance

expires_at
    nullable expiration state
    None means "never expires"
```

## Goals / Non-Goals

**Goals:**

- Introduce a tools cache domain dataclass, mapper, and repository matching newer persistence units.
- Keep `ToolsCacheDB` as the only SQLAlchemy model for the existing table.
- Preserve deterministic cache keys, cache hit/miss behavior, explicit expiration checks, full upsert behavior, deletion, and expired-entry cleanup.
- Correct `created_at` defaulting so each new domain object receives its own creation timestamp.
- Add domain, mapper, and repository tests beside legacy tests, then migrate production callers in reviewable feature groups.
- Remove legacy CRUD/schema access only after production and test references are gone.

**Non-Goals:**

- No database migration or schema change.
- No external API or OpenAPI change.
- No cache backend replacement, distributed cache, in-memory cache, eviction policy, or serialization redesign.
- No automatic deletion of an expired entry during `get`; callers retain the current explicit expiration check behavior.
- No clock abstraction or timezone migration in this change.

## Decisions

### 1. Keep One SQLAlchemy Model

`ToolsCacheDB` remains the only DB model and table definition for `tools_cache`. The new model is a feature-level dataclass mapped to and from `ToolsCacheDB`.

**Rationale**: The table already has the required shape. A second SQLAlchemy representation would duplicate ownership and create migration risk without improving the domain boundary.

**Alternative considered**: Create a parallel SQLAlchemy model. Rejected because it adds competing metadata for the same table.

### 2. Use One Full-State Domain Model

The domain model should represent both new and persisted entries:

```
ToolsCache(
    key: str,
    value: str,
    created_at: datetime = field(default_factory=datetime.now),
    expires_at: datetime | None = None,
)
```

It retains `is_expired()` behavior. `expires_at = None` is meaningful state and means the entry never expires.

**Rationale**: Cache writes are internal and always contain the complete entry state. A separate save/draft model would reproduce the legacy split without adding safety.

**Alternative considered**: Keep `ToolsCacheSave` beside the domain model. Rejected because there is no distinct create-only or partial-update shape.

### 3. Correct `created_at` to a Per-Instance Default

The domain dataclass uses `field(default_factory = datetime.now)`. Repository conversion always writes the domain timestamp explicitly.

On insert, `created_at` records construction time. On update, `save` writes the supplied full object, including `created_at`; callers currently construct a fresh entry when refreshing cache content, so a refresh receives a fresh timestamp.

**Rationale**: The existing Pydantic declaration evaluates `datetime.now()` at import time and can reuse that stale timestamp for every omitted `created_at`. No production consumer reads `created_at`, and expiration cleanup depends only on `expires_at`, so correcting this is isolated and testable.

**Alternative considered**: Preserve the existing row timestamp during upsert. Rejected because `save` is full replacement and callers are replacing the cache entry, not patching individual fields.

### 4. Keep Deterministic Key Creation at the Domain Boundary

The domain model exposes the existing deterministic key creation behavior using the same algorithm:

1. Base64-encode prefix and identifier separately.
2. Join them with `~`.
3. Return the MD5 digest through the existing `digest_md5` helper.

Callers use the domain helper rather than a repository method.

**Rationale**: Key derivation defines cache identity but does not access persistence. Keeping it with the domain model avoids making callers resolve a database dependency for a pure function while preserving the exact stored-key format.

**Alternative considered**: Keep `create_key` on the repository for a one-for-one CRUD replacement. Rejected because it keeps unrelated domain behavior on the persistence boundary.

### 5. Expose a Narrow Repository Surface

The repository provides:

- `get(key) -> ToolsCache | None`
- `get_all(skip, limit) -> list[ToolsCache]`
- `save(entry) -> ToolsCache`
- `delete(key) -> ToolsCache | None`
- `delete_expired() -> int`

`save` performs an exact full-object upsert:

```
                 ┌──────────────────────┐
                 │ ToolsCache domain    │
                 │ complete entry state │
                 └──────────┬───────────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
      no existing key                existing key found
             │                             │
             ▼                             ▼
       insert all fields              replace all fields
```

There are no separate public `create` and `update` methods because production callers use upsert semantics and do not need partial updates.

**Rationale**: A smaller repository API makes the intended cache behavior explicit and avoids carrying CRUD mechanics that only legacy persistence tests use.

**Alternative considered**: Mirror every CRUD method. Rejected because `create` and `update` have no production caller and are both covered by `save` behavior.

### 6. Migrate Consumers by Feature Group

The repository is added to DI while legacy CRUD remains available. Callers then migrate in bounded groups:

1. Domain, mapper, repository, DI, SQL test helper, and focused tests.
2. Currency exchange-rate caching.
3. Web browsing, HTML cleanup, and Twitter caching.
4. Chat attachment caching and related responder/support mocks.
5. Scheduled expired-entry cleanup.
6. Remove legacy DI, CRUD, schema, and tests after all references are gone.

**Rationale**: Cache persistence has many consumers but no single service owner. Feature-group migration keeps failures attributable and preserves manual review checkpoints.

**Alternative considered**: Replace every cache caller in one pass. Rejected because the web-browsing and chat test surfaces are broad enough to warrant separate checkpoints.

## Risks / Trade-offs

- **Deterministic key output changes and existing cache entries become unreachable** -> Keep the exact algorithm and add a golden-output test for the existing prefix/identifier example.
- **`created_at` correction changes stored timestamps on refreshed entries** -> Specify full replacement explicitly and test insert/update timestamps; no current caller reads this field.
- **`expires_at = None` is mistaken for an absent update** -> Mapper/repository tests must cover clearing expiration and never-expiring entries.
- **Expired entries begin disappearing during reads** -> Keep `get` as a raw lookup and retain explicit domain expiration checks in consumers.
- **Mixed DB/Pydantic/domain cache shapes during migration** -> Migrate one feature group at a time and keep focused tests green before removing legacy access.
- **Tests currently return dictionaries or Pydantic cache models from mocks** -> Update mocks to return the domain dataclass as each caller migrates.

## Migration Plan

1. Add the domain model, mapper, repository, DI property, and SQL test helper beside the existing CRUD/schema.
2. Add domain, mapper, and repository tests covering identity, timestamp, expiration, upsert, deletion, and cleanup semantics.
3. Migrate currency cache consumers and tests.
4. Migrate web browsing, HTML cleanup, Twitter cache consumers, and tests.
5. Migrate chat attachment cache consumers and related support mocks/tests.
6. Migrate scheduled cleanup to the repository.
7. Remove legacy DI access, CRUD/schema tests, CRUD/schema files, and SQL test helper after reference searches are clean.
8. Run the full offline test suite, all-files pre-commit, and strict OpenSpec validation.

Rollback remains straightforward because the database schema and deterministic key format do not change, and legacy CRUD remains available until the final cleanup milestone.

## Open Questions

None. Cache writes are internal full-state replacements, and the current caller/test surface defines the required behavior.
