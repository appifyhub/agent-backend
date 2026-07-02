## Code Style

### Python

In Python, I want you to use the latest type syntax (`type | None`) instead of `Optional`. I also want you to use a single space (`=`) around the equals sign (`=`) in function argument calls. It's important to use double quotation marks (`"`) instead of single quotations (`'`). And finally, we want to always use trailing commas in multi-line function declarations and calls. There's never a reason to write `unittest.main()` manually, we have a script for running tests. Never use inline imports inside of functions (use file header even in tests), and always use `from ... import ...` syntax at the top of the file.

### Comments

- For new code, avoid comments unless the logic is genuinely complex or the block is long
- When editing existing code, prefer updating comments over deleting them
- Comments should start with a lowercase letter, except in documentation or where grammar requires it

### Error Handling

Never use generic `ValueError`, `AssertionError`, or bare `Exception` for raising errors. Always use the structured exceptions from `util.errors` (`ValidationError`, `NotFoundError`, `AuthorizationError`, `ExternalServiceError`, `RateLimitError`, `ConfigurationError`, `InternalError`). Each raise must include an error code from `util.error_codes`. When re-raising from a caught exception, always use `raise ... from e` to preserve the chain. When calling external services (LLMs, image APIs, web fetchers), always guard against empty/null/empty-array responses with `ExternalServiceError`.

---

## MANDATORY PROJECT RULES

### Environment Management

- ALWAYS use `pipenv` for dependency management and Python command execution
- ALL commands must be run from project root (where Pipfile exists)
- Never use `pip` directly - always use `pipenv install` or `pipenv run`

### Database Migrations

- Ask the user to run `./tools/db_generate_migration -y` to generate new Alembic migrations (auto-generates based on model changes)
- Ask the user to run `./tools/db_apply_migration` to apply migrations to database (only with user's approval)
- Always check if model imports in `src/db/alembic/env.py` are up to date before running `db_generate_migration`

### Development Workflow

- Use `pipenv install --dev` and `pipenv run python src/main.py --dev` for development server (includes hot reload, verbose logging, dev API key)
- For code quality checks, run tools directly on changed Python files: `pipenv run ruff check --fix <files>` and `pipenv run python tools/check_spacing.py --fix <files>`
- For version bumps, run `./tools/bump_version {major|minor|patch}`; major and minor bumps reset lower version segments, and the script updates both project config and API docs
- Use `pipenv install` and `pipenv run python src/main.py` for production runs
- For all other operations like testing, always run inside of `pipenv`

### Code Quality

- Always run linting on changed Python files before commits: `pipenv run ruff check --fix <files>` and `pipenv run python tools/check_spacing.py --fix <files>`
- All scripts handle environment setup automatically (PYTHONPATH, .env files)

### Project Structure

- All scripts are in `tools` directory and use common `messages` for colored output
- Scripts validate project root location and fail safely if run from wrong directory
- You can see the CI/CD pipeline in `.github/workflows` directory
- You can see the API docs in `docs/` directory (keep it updated!)
