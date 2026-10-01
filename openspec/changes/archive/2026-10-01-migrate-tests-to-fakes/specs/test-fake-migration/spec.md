## Purpose

Make the transition to real application wiring and shared fakes complete, reviewable, and durable across the entire test suite and the agent instructions used to maintain it.

## ADDED Requirements

### Requirement: Every test module is accounted for

The migration SHALL track every existing test module through a complete review or conversion. Modules added during the migration SHALL also be included before completion. Already compliant tests SHALL retain suitable real implementations without introducing artificial fakes merely to change a file.

#### Scenario: Module without mocks
- **WHEN** a module already uses real pure functions or local infrastructure with valid shared data factories
- **THEN** it is explicitly reviewed and verified and can be marked complete without unnecessary edits

#### Scenario: Module added during migration
- **WHEN** final inventory finds a test module absent from the initial plan
- **THEN** it receives a review or migration assignment before the change is completed

### Requirement: Owned code is not mocked

Completed modules SHALL use real project implementations or explicit behavioral fakes instead of mocks, spies implemented with mocking tools, monkeypatched methods, or patched functions belonging to the project. Shared data factories SHALL continue to supply model objects. Narrow mocks SHALL be permitted only for system facilities or external dependencies that cannot reasonably be faked, with a specific rationale for each exception.

The managed test helper MAY temporarily wrap the DI initializer solely to forward its context-local interceptor through the existing constructor argument. This narrow test-harness exception SHALL execute the real initializer and restore it on exit; it SHALL NOT replace project behavior or authorize patches in individual consumer tests.

#### Scenario: Service effects stay at the repository contract
- **WHEN** a migrated service test verifies a membership update
- **THEN** it inspects saved values through repository getters without inspecting SQL, sessions, or SQLAlchemy events

### Requirement: Normal components are preferred

The migration SHALL NOT make a change unless it is needed. Tests SHALL use normal components whenever they work in the isolated offline environment, including real repositories in service tests. A fake SHALL be introduced only for a concrete need, such as external access or a failure that cannot reasonably be reproduced locally. Existing and newly introduced fakes SHALL be reviewed against this rule; unnecessary replacements and their unused support SHALL be removed. Using a real collaborator SHALL NOT expand assertions into that collaborator's implementation.

#### Scenario: Repository already works locally
- **WHEN** a service test needs ordinary repository save, lookup, or deletion behavior available in isolated SQLite
- **THEN** it uses the normal DI repository and public getters without introducing a repository fake

#### Scenario: External behavior needs a substitute
- **WHEN** a scenario requires an external response or failure unavailable through suitable local components
- **THEN** it uses a focused fake at an existing contract and keeps the remaining suitable components real

### Requirement: Stay in the subject's layer

Unit tests SHALL assume that dependencies satisfy their contracts and SHALL NOT test those dependencies' implementations. Service tests SHALL verify service results through return values and repository getters, without validating sessions, database state, SQL, or rollback ordering. A getter MAY be added to a test-only fake when needed. If a case cannot be meaningfully verified at the subject's layer, it MAY be omitted rather than crossing layers.

#### Scenario: Membership service changes a membership
- **WHEN** a service test runs a membership update
- **THEN** it checks the returned membership and the repository getter's result without configuring or observing a session

### Requirement: Production code is not changed for testability

Further migration work SHALL NOT change production code merely to enable tests, add getters, expose internal state, or create injection points. The consistency review specifically authorizes separating base chat-model construction from its accounting decorator in DI, following the existing base-client/decorator pattern. The subsequent session review authorizes a thin DI adapter over unchanged SQL helpers that preserves existing sessionless background construction, plus initial session injection to avoid constructing two ingress containers. Context-local interception SHALL remain entirely in test support. Tests SHALL otherwise use existing interfaces and test-side support. Previously completed production changes are historical work, not authorization for more test-enabling refactors.

#### Scenario: No suitable getter exists
- **WHEN** a test needs an observation that production does not expose
- **THEN** it uses a test-only fake getter or omits the unobservable case, without modifying production code

#### Scenario: System exception
- **WHEN** a test needs a system failure that cannot reasonably be reproduced through its fake or local infrastructure
- **THEN** it can retain a narrowly scoped system-level mock with an explicit explanation and without mocking the application wrapper

### Requirement: Complete review milestones

Test modules SHALL be assigned to logical, bounded review batches based on feature boundaries and actual diff complexity. Related modules MAY share a batch regardless of source-file length. Feature repositories SHALL stay with their feature modules, while caches and shared infrastructure MAY be reviewed together. A batch SHALL include its required production boundaries, shared fake behavior, migrated assertions, and verification rather than leaving a listed module partly converted. Execution SHALL stop after every review batch until the user explicitly approves continuation.

#### Scenario: Checks pass
- **WHEN** all migration tasks and checks for a milestone pass
- **THEN** the agent presents the completed slice for manual review and does not begin the next milestone

#### Scenario: Review requests changes
- **WHEN** the user requests corrections to the completed slice
- **THEN** those corrections remain within that milestone and do not authorize work on the next one

### Requirement: Behavior coverage survives migration

The migration SHALL preserve meaningful success, failure, and side-effect coverage observable at the subject's layer. It SHALL NOT preserve an old mock assertion by inspecting dependency internals, tracing lower-layer operations, or changing production code. A case without meaningful same-layer verification MAY be removed. Migrated tests SHALL run offline, and the final suite SHALL pass before the migration is reported complete.

Existing core DI coverage SHALL be reused. New DI tests SHALL be added only for a special new production DI feature whose failure could break application behavior. Ordinary dependency construction, fixtures, and test-helper implementation details SHALL NOT justify additional DI tests. Redundant cases SHALL be removed rather than moved to another test module. The final agent-instructions milestone SHALL document this rule.

#### Scenario: Expected absence of external work
- **WHEN** an existing test asserts that a cache hit avoids an external call
- **THEN** its migrated form verifies the returned result and the absence of requests in the external fake's observations

### Requirement: Agent instructions describe the completed setup

After module migration, all active agent-rule files containing the existing test-data policy or equivalent testing instructions SHALL be read in full before being updated consistently. A concise testing subsection SHALL explain shared data factories, production-container-based setup via `self.di = self.enterContext(di_for_tests())` in `setUp` and its automatic cleanup, the equivalent context-manager form, default fakes and explicit overrides, preference for suitable normal components, the existing isolated SQLite setup for real repositories in service and repository tests, temporary storage, offline operation, local configuration cleanup, and the narrow system/external mock exception policy. It SHALL explicitly prohibit unnecessary changes and using fakes when normal components work. It SHALL require class-level type declarations for all instance attributes assigned through `self`, including in `__init__` and `setUp`. This work SHALL remain in the final agent-rules milestone.

Configuration guidance SHALL include an explicit example registering `self.addCleanup(setattr, config, "web_retries", config.web_retries)` before mutation, explain restoration after setup/test failure, and cover local restoration of mutated dictionaries, environment variables, and singleton state where those are changed. It SHALL prohibit introducing global config-reset fixtures. The subsection SHALL also document verified parallel defaults and serial/fixed-worker overrides.

The subsection SHALL explicitly require staying in the starting layer, assuming dependencies work, using public getters or test-only fake getters for observations, omitting cases that cannot be verified at that layer, and never changing production code merely to enable tests. All fake implementation filenames SHALL start with `fake_`.

The final testing subsection SHALL use one introductory paragraph and several concise bullets, reflecting the user's review correction. It SHALL summarize the core testing rules and reference existing helper documentation for interception and resource-lifetime mechanics, rather than repeat the detailed decision checklist at tasks 61.3a–61.3j. General style guidance SHALL remain in its appropriate existing sections. The instructions SHALL describe the final SQLUtil-free setup and only parallel behavior that was actually verified.

#### Scenario: Final rule search
- **WHEN** the final audit searches visible and hidden agent-rule files for the old policy and equivalent wording
- **THEN** every applicable active rule file reflects the new setup while unrelated rules and historical change records remain intact

#### Scenario: Later review decisions survive the instruction update
- **WHEN** the final milestone updates agent instructions
- **THEN** the consolidated decision checklist is reconciled against the implemented setup, with core rules summarized concisely and implementation mechanics left in existing helper documentation
- **AND** superseded experiments are not presented as current guidance

### Requirement: Parallel execution is verified before becoming the default

A separate later milestone SHALL verify the migrated suite under serial and multiple-worker execution using pytest-xdist. Verification SHALL cover equivalent test collection and behavior, repeated concurrent runs, shared-resource isolation, offline operation, cleanup, and available local/CI resource limits. Automatic CPU-based worker selection SHALL become the default only after verification, with serial and fixed-worker overrides retained.

#### Scenario: Parallel verification succeeds
- **WHEN** serial, two-worker, and automatic-worker runs preserve the suite's behavior and resource isolation
- **THEN** the automatic-worker default can be configured and presented at its own manual-review gate before the final agent-instructions milestone

#### Scenario: Workers interfere or exceed available resources
- **WHEN** parallel verification exposes shared paths, databases, unfinished background work, or unsuitable worker counts
- **THEN** the milestone resolves the demonstrated issue and re-verifies before enabling the default, recording any unavailable environment verification
