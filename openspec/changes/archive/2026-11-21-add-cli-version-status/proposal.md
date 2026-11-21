# Proposal

## Why

CLI `status` needs to show backend health and warn about newer CLI releases even when the client is disconnected or locked. One public response supplies both kinds of information while leaving operational health probes independent of GitHub and the metadata cache.

## What Changes

- Add public `GET /cli/status` with backend `status` and `service_version`, matching the values from `/health`, and `cli_version`, a normalized semantic version or JSON `null` when disabled or unavailable. The CLI needs only this request. `GET /health` keeps its existing payload and independent behavior, and existing CLI authentication stays unchanged.
- Read a deployment-selected raw `VERSION` URL from `CLI_VERSION_URL`. Share successful lookups across API instances for one hour using the existing database tools cache. Do not cache failures or serve stale versions.
- As the final milestone, explicitly protect `GET /cli/status` in the API Helm chart at the existing CLI rate and verify `/health` retains its own limiter. Document the environment-specific source and owner rollout.
- **BREAKING (companion CLI change):** `status` absorbs `server` without an alias. Default `status` prints local readiness first, then backend health, and warns on stderr only for a newer CLI. Its exit code reports local readiness, not backend health. `status --offline` keeps the local-only report.

## Capabilities

### New Capabilities

- `cli-version-status`: Public backend status and deployment-specific CLI version discovery in one response, including metadata availability, freshness and ingress limits.

### Modified Capabilities

## Impact

Backend configuration, CLI feature code and DI, FastAPI routing, `docs/open-api-docs.yaml`, offline tests, and a final owner-reviewed change in `../charts/the-agent-api`. No database migration, new cache infrastructure, CLI implementation, web change or live deployment edits. The companion CLI proposal owns command removal, output, SemVer comparison, and migration of registration, completion, help, catalog, tests, docs and embedded agent guidance.
