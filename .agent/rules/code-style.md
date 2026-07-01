---
trigger: always_on
---

### Code style

#### Python

In Python, I want you to use the latest type syntax (`type | None`) instead of `Optional`. I also want you to use a single space (`=`) around the equals sign (`=`) in function argument calls. It's important to use double quotation marks (`"`) instead of single quotations (`'`). And finally, we want to always use trailing commas in multi-line function declarations and calls. There's never a reason to write `unittest.main()` manually, we have a script for running tests. Never use inline imports inside of functions (use file header even in tests), and always use `from ... import ...` syntax at the top of the file.

#### Comments

- For new code, avoid comments unless the logic is genuinely complex or the block is long
- When editing existing code, prefer updating comments over deleting them
- Comments should start with a lowercase letter, except in documentation or where grammar requires it

#### Error Handling

Never use generic `ValueError`, `AssertionError`, or bare `Exception` for raising errors. Always use the structured exceptions from `util.errors` (`ValidationError`, `NotFoundError`, `AuthorizationError`, `ExternalServiceError`, `RateLimitError`, `ConfigurationError`, `InternalError`). Each raise must include an error code from `util.error_codes`. When re-raising from a caught exception, always use `raise ... from e` to preserve the chain. When calling external services (LLMs, image APIs, web fetchers), always guard against empty/null/empty-array responses with `ExternalServiceError`.
