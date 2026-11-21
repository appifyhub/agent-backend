# Design

## Context

`src/main.py` serves `/health` directly from `config.version`; the chart uses it for both readiness and liveness. The CLI routes either redeem a connect key or validate a token. Neither flow is appropriate for metadata. `ToolsCacheRepository.get()` returns expired rows too; its `save()` commits to the shared database. `DI.http_client()` provides Requests in production and is intercepted by the shared offline HTTP fake in tests.

## Goals / Non-Goals

Provide backend status and optional, deployment-specific CLI update metadata in one anonymous response. Do not add a release registry, user/account checks, an in-process version cache, a migration, a worker, distributed locking or application-level throttling. Do not alter the CLI, web app, health handler, existing cache cleanup or ingress architecture.

## Decisions

1. **Choose the source at deployment.** Add a non-secret `cli_version_url` to `src/util/config.py`, read from `CLI_VERSION_URL` with an empty default. The existing environment reader trims whitespace. A blank setting short-circuits before cache or network access. Only the configured URL goes to the HTTP client; the route accepts no source parameter. Do not derive it from hostname, branch, app version or credentials.
2. **Let one CLI feature service own lookup and freshness.** Use request-scoped DI, no invoker. Read `ToolsCache.create_key("cli-version", configured_url)` through `di.tools_cache_repo`. If the entry is unexpired and valid, return its normalized value without rewriting it. Treat a malformed entry as a miss. On miss or expiry, fetch and validate before saving a `ToolsCache` with expiry one hour from refresh. Return the new version only after a successful save. On database read/write failure, roll back the failed request transaction using DI and return unavailable; never substitute stale data or bypass the cache on database outage. Do not negative-cache failures.
3. **Use the low-level injected GET, not `WebFetcher.fetch_html()`.** The latter loops over `config.web_retries`, sleeps between attempts, reads the whole body and has different cache semantics. GET the configured raw URL once with `stream=True`, `allow_redirects=False` and `timeout=2`; no token, generic retry loop or sleep. Require HTTP 200. Read in bounded chunks, reject more than 1024 bytes *before* trimming, regardless of `Content-Length`, and close the response on every path. Decode as ASCII, strip surrounding whitespace and one optional lowercase `v`, then full-match the SemVer 2.0.0 grammar. Preserve prerelease/build identifiers; reject extra text, partial versions and forbidden leading zeroes. A grammar match suffices: the backend does not compare or order versions. Transport, decoding and content failures yield unavailable, not a new public error code.
4. **Combine backend status and optional CLI metadata.** Add `GET /cli/status` beside the CLI routes with a request DB session and `DI(db)` only. The response requires `status` and `service_version`, matching `/health`'s `status` and `version`, respectively. The optional `cli_version` is a normalized SemVer string or `null`. Metadata unavailability never removes or changes the backend fields. Document `security: []` to override the OpenAPI document's global bearer requirement. Do not reuse the token/account status path. `GET /health` continues to return backend status and backend version directly, without reading the tools cache or contacting the version source.
5. **Append an exact chart route, do not replace the broad one.** `../charts/the-agent-api/values.yaml` already lists `POST /cli/connect` and `^/cli/` with average 10. Append `{method: GET, path: /cli/status, average: 10}` to preserve existing route indexes and middleware names. Existing templates give exact paths priority 1001 and regexps 1000; explicit `average` selects an indexed middleware inheriting period `1m`, burst `5` and IPv6 `/64`. The status allowance is now separate from the broad CLI bucket, at the same rate. Omitting `average` would silently select the global average of 5. Keep existing flags, general ingress, templates and other routes unchanged.

### Consumer contract (implemented in the companion CLI change)

`status` evaluates local readiness once and prints that report first. `--offline` stops there: no network, health section or update warning. Hard local errors such as bad config or token data propagate without requests. A normal connected, disconnected, locked or expired report with a valid effective backend URL uses the existing URL precedence and makes one anonymous `GET /cli/status` within a three-second context budget. Measure latency for that request. Do not unlock the keychain, retry, call `/health` as a fallback, query GitHub directly or maintain a CLI cache.

After local stdout, render the backend status (including non-`ok` values), backend version and request latency to stdout with terminal sanitization. Then print a warning to stderr only for a usable `cli_version` that is newer by the existing SemVer comparison rules. Missing, null or invalid CLI metadata suppresses only the warning. If there is no usable effective URL or the combined request fails (including a 404 from an older backend or an edge 429), print the catalog-backed `Backend unavailable` without an update warning. Remote outcomes do not change the local exit code (0 or 3); caller cancellation and output I/O errors still propagate.

## Risks / Trade-offs

- **Timeout semantics:** Requests' scalar timeout applies to connection and socket read inactivity, not total elapsed time (including DNS and a trickling response). The byte cap and no redirects/retries limit work; the CLI independently enforces a three-second overall context deadline. Do not claim or simulate a backend wall-clock deadline with a background thread.
- **Concurrent cold misses:** Separate instances can fetch the same URL concurrently. An insert race is handled like another cache write failure; the affected response can be null. A subsequent request can read the winner's row. No distributed coordination.
- **Release timing:** Readers may observe a previous version for up to one hour, or the release branch's `VERSION` before binaries exist. Both are accepted. No GitHub Releases lookup or alternate source.

## Migration Plan

Deploy the additive API with lookup disabled by default; no database rollout. In the final chart milestone expose `config.values.CLI_VERSION_URL` (default `""`) through the existing ConfigMap/`envFrom`. Update the chart README and use the chart's minor-version convention for changes to default limited routes (currently `0.9.0` → `0.10.0` if unchanged).

**BREAKING for CLI callers:** Replace `server` with `status` for the report; no compatibility alias remains. Scripts that used the old `server` failure exit as a health probe must check `/health` directly and evaluate its status. The combined command's exit code reflects local readiness, even when the backend is unavailable or reports a non-`ok` status.

The deployment owner sets the full URL and rolls API pods so they receive the new environment:

| Environment | `config.values.CLI_VERSION_URL` |
| --- | --- |
| Staging | `https://raw.githubusercontent.com/appifyhub/agent-cli/main/VERSION` |
| Production | `https://raw.githubusercontent.com/appifyhub/agent-cli/release/VERSION` |

Enable `ingress.rateLimit.enabled` where required. Helm replaces lists, so owners overriding `ingress.rateLimit.routes` must retain their existing entries and append the exact status entry. Hand off fields and example values only: do not open, list, search or edit `../charts/continuous-deployment/argo`. Roll back discovery by clearing the URL and rolling pods; leave rate protection in place. Earlier API images may lack the combined endpoint; the CLI reports backend information unavailable rather than issuing a second request.
