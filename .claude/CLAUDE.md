# Project Rules — Backend (Python)

> General code style and behavioral rules are in `~/.claude/CLAUDE.md`.

## Code Style

### Python

- Use `type | None` instead of `Optional`, double quotes instead of single quotes, a single space around `=` in call arguments, and trailing commas in multiline declarations and calls.
- Declare every `self` attribute at class level with its type, including attributes assigned in `__init__` or `setUp`. Initialize fresh mutable state per instance or test; class-level declarations are not shared mutable instances.
- Keep imports at the file header, including in tests, using `from ... import ...`; prefer module-qualified calls for ambiguous names such as `asyncio.run`. Never use inline imports except for production DI’s lazy provider imports that avoid cycles. Add `TYPE_CHECKING` imports only for annotations that use them.
- Do not change working code without a concrete need. Avoid single-use abstractions, unnecessary files, and helpers that only forward another call. Keep a local default constant with its owning implementation, and dependency-specific options on their factories rather than the DI constructor.

### Testing

Construct DI-managed subjects with `self.di = self.enterContext(di_for_tests())` in `setUp`, or `with di_for_tests() as di:`. The helper provides real repositories on isolated SQLite, temporary local storage, shared offline fakes, and cleanup even after setup/test failure. Pure functions need no DI. See `test/util/di_utils.py` for interception and resource-lifetime details.

- Never mock or manually construct data, database, domain, API, or vendor model objects in tests; add or update the corresponding factory in `test/stubs/` and use it. Override only fields relevant to the scenario.
- Keep the subject and suitable collaborators real; do not introduce fakes or production changes merely for tests. Stay in the tested layer and assume dependencies work. Assert through public APIs/repository getters, never SQL or session internals through a repository. Use a test-only fake getter or omit an unobservable case.
- Reuse existing DI fakes and registrations; add only necessary external behavior in `test/fakes/fake_*.py`. Keep adapters and usage decorators real. Configure the shared HTTP fake for GET/POST; direct `requests` calls are already forwarded, and unconfigured requests fail offline. Never mock owned behavior; justify each unavoidable system/external patch.
- Preserve session ownership and keep background work offline. Use fresh session scopes for workers, propagate interceptor policy without retaining request sessions, and finish workers before environment cleanup. Do not add fake sessions, model catalogs, or competing repository factories.
- Change public config properties directly and restore only changed state locally. Register `self.addCleanup(setattr, config, "web_retries", config.web_retries)` before `config.web_retries = 0`; likewise restore changed dictionaries, environment, or singleton state. No config wrappers or global reset fixtures; DI does not reset config.
- Test behavior, not routine construction or every DI provider. Add DI coverage only for a new production behavior with a concrete failure risk. Match tests to production subjects, reuse existing modules, and ask before creating new test files.
- Always run tests offline with `pipenv run pytest -v`; never write `unittest.main()` manually. Workers are automatic (`-n 0` for serial, `-n 2` for a fixed count). Run required Ruff/spacing checks. Deliver coherent module milestones, stop for review, and briefly report what finished and what comes next.

### Comments

- For new code, avoid comments unless the logic is genuinely complex or the block is long
- When editing existing code, prefer updating comments over deleting them
- Start short ordinary comments with lowercase, except where grammar requires otherwise. Use normal sentence-case pydoc docstrings for multiline explanations. Explain unusual concurrency/resource ownership where needed; avoid trivial comments.

## Error Handling

Never use generic `ValueError`, `AssertionError`, or bare `Exception` for raising errors. Always use the structured exceptions from `util.errors` (`ValidationError`, `NotFoundError`, `AuthorizationError`, `ExternalServiceError`, `RateLimitError`, `ConfigurationError`, `InternalError`). Each raise must include an error code from `util.error_codes`. When re-raising from a caught exception, always use `raise ... from e` to preserve the chain. When calling external services (LLMs, image APIs, web fetchers), always guard against empty/null/empty-array responses with `ExternalServiceError`.

## Environment Management

- ALWAYS use `pipenv` for dependency management and Python command execution
- ALL commands must be run from project root (where Pipfile exists)
- Never use `pip` directly - always use `pipenv install` or `pipenv run`

## Database Migrations

- Ask the user to run `./tools/db_generate_migration -y` to generate new Alembic migrations (auto-generates based on model changes)
- Ask the user to run `./tools/db_apply_migration` to apply migrations to database (only with user's approval)
- Always check if model imports in `src/db/alembic/env.py` are up to date before running `db_generate_migration`

## Development Workflow

- Use `pipenv install --dev` and `pipenv run python src/main.py --dev` for development server (includes hot reload, verbose logging, dev API key)
- For code quality checks, run tools directly on changed Python files: `pipenv run ruff check --fix <files>` and `pipenv run python tools/check_spacing.py --fix <files>`
- For version bumps, run `./tools/bump_version {major|minor|patch}`; major and minor bumps reset lower version segments, and the script updates both project config and API docs
- Use `pipenv install` and `pipenv run python src/main.py` for production runs
- For all other operations like testing, always run inside of `pipenv`

## Code Quality

- Always run linting on changed Python files before commits: `pipenv run ruff check --fix <files>` and `pipenv run python tools/check_spacing.py --fix <files>`
- All scripts handle environment setup automatically (PYTHONPATH, .env files)

## Project Structure

- All scripts are in `tools` directory and use common `messages` for colored output
- Scripts validate project root location and fail safely if run from wrong directory
- You can see other rules in `.cursor` directory, if you need those rules
- You can see the CI/CD pipeline in `.github/workflows` directory
- You can see the API docs in `docs/` directory (keep it updated!)
