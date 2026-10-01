## Why

The suite now builds test data through shared stubs, but many tests still mock DI, repositories, services, and individual methods. Tests should use normal components wherever they work in the isolated offline environment, with behavioral fakes only for dependencies that require a substitute. Assertions stay at the subject's public boundary.

## What Changes

- Add optional return-type-based interception to the existing DI class. Resolve replacements before ordinary construction, use `None` for unhandled requests, propagate interceptor errors, preserve dependency lifetimes, and carry the interceptor through `clone()` without copying context-bound instances. Do not introduce a DI subclass.
- Keep SQL creation and cleanup unchanged behind the intercepted `DI.new_session()` context-manager adapter. In `di_utils.py`, scope a context-local interceptor and temporarily forward it through the real DI initializer so fresh background instances keep the existing sessionless orchestration and independent session boundaries. Production DI has no ambient interceptor.
- Let each responder attach its initial session with `DI.inject_db_session()` and use one DI for ingress. Reject subsequent session injection; use clones for separate session scopes and retain SQL's cleanup ownership.
- Add test-side registration and type-resolution support, shared fakes under `test/fakes/fake_*.py`, and a resource-owning `di_for_tests(interceptor = ...)` helper. Per-test overrides precede shared test defaults; unhandled dependencies use production construction.
- Do not make unnecessary changes or introduce a fake when a normal component works. Keep real repositories backed by the existing isolated SQLite environment, including in service tests, and use real temporary local storage. Add a fake only for a concrete need such as external access or a failure that cannot reasonably be reproduced locally. Do not emulate SQLAlchemy sessions or SQL. Repository setup replaces SQLUtil with production DI without changing production repositories.
- Use existing public interfaces and DI interception to supply fakes. Stay in the layer under test and assume dependencies fulfill their contracts. Observe results through public getters, add a getter to a test-only fake if needed, or omit a case that cannot be observed at that layer. Do not change production code to enable tests or add observability.
- Review and migrate all 120 current test modules. Group review batches by feature boundaries and actual change complexity; related modules may share a batch regardless of source-file length. Keep feature repositories with their feature modules, and group caches/shared infrastructure together. Retain mocks only for system facilities or external dependencies that cannot reasonably be faked; never mock project behavior. The managed test helper may temporarily wrap the real DI initializer solely to supply its existing interceptor argument.
- Stop after every completed milestone for the user's manual review. Passing checks do not authorize starting the next milestone.
- Verify parallel execution in a separate later milestone using pytest-xdist: audit shared resources, compare serial and concurrent runs, and enable automatic CPU-based worker selection only after verification.
- Finish with a suite-wide mock audit, offline verification, and consistent updates to all matching AI agent rules.

## Capabilities

### New Capabilities

- `di-interception`: Optional dependency replacement on the production DI, including type identity, factory arguments, caching, fallback, and clone behavior.
- `test-dependency-environment`: Isolated test DI construction, shared behavioral fakes, real local infrastructure, and offline resource lifecycles.
- `test-fake-migration`: Complete module coverage, permitted mock exceptions, review-gated milestones, and agent instructions for the new setup.

### Modified Capabilities

None. There are no existing specifications under `openspec/specs/` to amend.

## Impact

- Production: retain explicit DI interception, HTTP construction support, and the reviewed base-model/accounting separation. Keep the approved session adapter and delegate chat, image-worker, and video-worker session scopes through it; keep context-local interception entirely in test support and leave `db/sql.py`, webhook signatures, and media-worker lifetimes unchanged. Further production refactors or observability changes are outside this migration.
- Tests: all current `test/**/test_*.py` modules, test SQL support, `test/stubs/`, and new reusable fake/helper modules. The later parallel-execution milestone adds pytest-xdist as a development dependency and verifies the local/CI execution settings.
- Agent rules: `AGENTS.md`, `GEMINI.md`, `.claude/CLAUDE.md`, `.cursor/rules/style.mdc`, `.windsurf/rules/rules.md`, and `.agent/rules/code-style.md`, plus any additional matching rule files found in the final search.
- Delivery: a foundation milestone, complete module migration milestones, and a final verification/rules milestone. Implementation pauses at each boundary until the user approves continuation.
