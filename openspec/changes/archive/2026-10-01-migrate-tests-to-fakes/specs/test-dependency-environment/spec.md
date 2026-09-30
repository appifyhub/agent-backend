## Purpose

Provide a repeatable offline test environment that constructs subjects and suitable normal collaborators through the production container, with explicit fakes only where needed.

## ADDED Requirements

### Requirement: Production container API in tests

The test setup helper SHALL expose an instance of the production container with its normal dependency API. It SHALL NOT substitute a mocked container or a test subclass. Resolution precedence SHALL be per-test interception, shared test defaults, then ordinary production construction.

#### Scenario: Ordinary application service
- **WHEN** a test requests a service without an explicit replacement
- **THEN** the real service is constructed by the production container using the environment's dependencies

#### Scenario: Override one external dependency
- **WHEN** a test provides an interceptor that handles one dependency and returns `None` for others
- **THEN** that dependency uses the per-test replacement and the remaining requests retain shared defaults or production construction

#### Scenario: Shared external defaults
- **WHEN** a test requests Telegram or WhatsApp SDK behavior through `di_for_tests()`
- **THEN** production SDKs and application services execute with the environment's shared fake bot APIs, without per-test duplicate registrations or live bot calls
- **AND** tests configure and inspect those fakes through the normal DI providers; an additional interceptor is reserved for a concrete override of the shared setup

### Requirement: Isolated unit dependencies and storage

Tests SHALL prefer normal components when they work in the isolated offline environment. Services MAY use real repositories through production DI with the existing isolated SQLite database; assertions SHALL remain on service results and repository getters. Fakes SHALL require a concrete need that suitable normal components cannot reasonably satisfy. The migration SHALL NOT implement fake SQLAlchemy sessions or SQL evaluation, or change production repositories to enable tests. The subject SHALL remain real and be constructed through production DI. The existing disk storage implementation SHALL be used with a temporary root when it meets the scenario's needs. Test records and structured inputs or responses SHALL be built through shared data factories. Unrelated environments SHALL NOT share data, stored files, or mutable fake state. Real repositories SHALL retain SQLite after SQLUtil removal.

#### Scenario: Service saves a membership
- **WHEN** a membership service test supplies external membership responses through the shared bot API fake and seeds membership state through the normal repository
- **THEN** it verifies the service's returned and saved membership values through repository getters without inspecting sessions, SQL, or Telegram parsing

#### Scenario: Repository unit test
- **WHEN** a repository is the subject under test
- **THEN** its real session comes from the test DI's isolated SQLite setup and the repository's own query, mapping, write, and failure behavior is verified

#### Scenario: Independent environments
- **WHEN** two test environments are created
- **THEN** data, files, and fake observations created in one are absent from the other

### Requirement: One repository construction path after migration

Test support SHALL own any needed fakes and local resources while production DI constructs application components. The completed migration SHALL remove all `SQLUtil` consumers and delete `test/db/sql_util.py`, without replacing it with another repository factory API. Test setup SHALL leave production database globals unchanged. Service tests SHALL NOT configure sessions or verify database behavior; they SHALL seed and observe their collaborators through public interfaces.

#### Scenario: Final database support audit
- **WHEN** the final migration milestone evaluates database test support
- **THEN** remaining SQLUtil consumers are migrated, the obsolete helper is deleted, and the complete suite passes without it

### Requirement: DI wiring is independent of database models

The test DI helper SHALL receive a session from database support without importing concrete database models, maintaining a model catalog, or inspecting or generating application data. Database support SHALL reuse the registered SQLAlchemy metadata rather than duplicate model registration or introduce unnecessary discovery. Necessary SQLite dialect adaptation SHALL derive from schema declarations in a separate metadata copy, without changing production metadata or ORM mappings and without callbacks that inspect application rows.

#### Scenario: Existing imports register the schema
- **WHEN** ordinary test imports already populate SQLAlchemy's metadata
- **THEN** database support creates the isolated schema from that metadata without a manually maintained model list or package scanner

### Requirement: Configuration follows the test lifecycle

Tests that require configuration changes SHALL assign public `config` properties directly and register local cleanup to restore the values they change, including after failure. The migration SHALL NOT introduce global configuration initialization or restoration fixtures. DI environment creation and cleanup SHALL NOT reset configuration.

#### Scenario: Settings applied before DI creation
- **WHEN** a test assigns configuration and opens one or more nested DI environments
- **THEN** those environments observe the test's settings, and closing them leaves the settings intact

#### Scenario: Configuration changes cannot leak between tests
- **WHEN** a test changes a config property or mutates a config dictionary and then finishes or fails
- **THEN** that test's local cleanup restores the values it changed before another test runs

### Requirement: Explicit external behavior

Shared fakes SHALL implement the consumed boundary contract and support the responses, failures, and state transitions required by their tests. All fake implementation modules SHALL have filenames beginning with `fake_`. Unexpected requests or exhausted response queues SHALL fail clearly rather than contact a live service or return an arbitrary success. Tests SHALL observe results through existing public interfaces or test-only fake getters, without replacing the subject's logic or testing dependency internals.

#### Scenario: Provider output and accounting
- **WHEN** a test supplies a fake provider response containing usage data
- **THEN** the wrapper under test processes that response and its normal accounting collaborators record the resulting usage and charge, observable through public repository getters

#### Scenario: Unconfigured HTTP request
- **WHEN** an application issues a request that the fake HTTP client has not been configured to handle
- **THEN** the test fails with a diagnostic identifying the request and no external network request is sent

#### Scenario: Direct requests transport in the managed environment
- **WHEN** application code calls requests.get or requests.post directly inside di_for_tests()
- **THEN** scoped transport forwarding uses the environment's shared default HTTP fake, configured through the normal DI provider
- **AND** GET and POST use separate response queues and request observations
- **AND** leaving the scope, including after failure, restores the enclosing transport without changing production code

#### Scenario: Simulated external failure
- **WHEN** a fake produces a configured provider or transport failure
- **THEN** the application's real error handling executes and the fake's configured failure does not trigger production fallback

#### Scenario: Shared model replacement below accounting
- **WHEN** a test needs controlled chat-model responses
- **THEN** it configures the environment's shared `FakeChatModel` through the base-model DI provider while the usage decorator and suitable accounting collaborators remain real
- **AND** no additional interceptor or usage-decorator replacement is needed, and unconfigured model calls fail without network access

#### Scenario: URL shortener in a consumer test
- **WHEN** a command or chat-agent test needs a predictable shortened link
- **THEN** it configures the environment's shared fake through the existing `UrlShortener` provider, without an additional interceptor or HTTP mocking in the consumer test

### Requirement: Consumer and adapter tests replace different boundaries

Tests of consumers SHALL keep suitable normal collaborators and replace a collaborator at its existing contract only when a concrete scenario requires it. Tests of an external adapter SHALL execute that adapter against a fake lower-level transport or client. Parsing, caching, retry, usage, and spending behavior SHALL execute in the tests of the unit that owns that behavior. Merely being a dependency, including an owned repository or service, SHALL NOT justify a fake.

#### Scenario: Fetcher cache behavior
- **WHEN** a fetcher test runs with a fake HTTP client and real cache repository in the isolated environment
- **THEN** the real fetcher performs parsing and cache updates, and its subsequent cache hit is verified through cache getters and the HTTP fake's request history

#### Scenario: Bot adapter behavior
- **WHEN** a bot adapter test substitutes only its HTTP transport
- **THEN** the real adapter creates and interprets the provider request and response

### Requirement: Offline operation and complete resource ownership

Test setup SHALL avoid live databases, provider services, and deployment credentials. Test environments SHALL clean up their owned sessions, any explicitly needed local resources, temporary files, and mutable replacement state on normal exit or failure. Background work SHALL remain offline and SHALL finish before its resources are destroyed. Tests SHALL use existing construction interfaces, with the reviewed base-model/accounting separation and session adapter. The helper SHALL scope its interceptor to the execution context, restoring the enclosing policy on exit. New session scopes SHALL use separate real sessions on the same isolated SQLite database. Sessionless background DI instances SHALL remain sessionless until they enter those scopes; tests SHALL NOT attach the parent session or pass its DI into background work.

#### Scenario: Cleanup after failure
- **WHEN** a test raises inside the managed environment
- **THEN** its owned sessions and temporary storage are still released

#### Scenario: Detached background session
- **WHEN** application work opens a detached session and clones its container
- **THEN** it retains the collaborator replacement policy and uses isolated test resources without reaching a live database

### Requirement: Test-only context-local interception preserves background boundaries

`di_utils.py` SHALL own `context_local_interceptor`. The managed test scope SHALL temporarily wrap the DI initializer to pass this interceptor through its existing argument when no explicit interceptor was supplied. The real initializer SHALL execute, and explicit interceptors SHALL take precedence. The helper SHALL restore both the enclosing context value and initializer on exit, including failure. This mechanism SHALL NOT add ambient behavior to production DI, attach a session to fresh sessionless containers, or copy another container's caches. Asyncio tasks and `asyncio.to_thread` work SHALL retain the scope's replacement policy without changing responder signatures.

#### Scenario: Fresh sessionless background container
- **WHEN** background chat work constructs DI inside the managed test execution context
- **THEN** the container has no attached session and resolves external dependencies through that context's interceptor
- **AND** its fresh session scopes use the isolated test database

#### Scenario: Nested scope exits
- **WHEN** an inner test environment finishes or fails
- **THEN** the enclosing initializer and context-local interceptor are restored for subsequent construction
