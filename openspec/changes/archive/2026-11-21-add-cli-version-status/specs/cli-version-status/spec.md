# Spec Delta

## Purpose

Let CLI `status` report backend health and discover the advertised CLI version with one request, without credentials or dependence on account state. Missing metadata does not hide usable backend information, and operational health probes remain independent.

## ADDED Requirements

### Requirement: Public CLI status response
The application SHALL answer `GET /cli/status` without a JWT, API key, connect key or user context. Its HTTP 200 JSON object SHALL require `status` and `service_version`, matching `/health`'s `status` and `version` respectively. The optional `cli_version` field is a normalized SemVer string when available. An omitted or null value means the CLI version is unavailable.

#### Scenario: Anonymous client checks a configured backend
- **WHEN** an unauthenticated client requests status and CLI version `1.2.3` is available on a healthy backend running version `5.0.0`
- **THEN** the response is HTTP 200 with `{"status":"ok","service_version":"5.0.0","cli_version":"1.2.3"}` and no account or credential information

#### Scenario: Cache is unavailable
- **WHEN** reading or saving version metadata in the shared cache fails
- **THEN** the response is HTTP 200 with `cli_version: null` and the usual backend `status` and `service_version` rather than a stale CLI version or an API error

### Requirement: Deployment selects the source
The backend SHALL fetch only the full raw root `VERSION` URL configured via `CLI_VERSION_URL`, without GitHub authentication. It SHALL NOT infer a branch, accept a client-selected source, or consult GitHub Releases.

#### Scenario: No configured source
- **WHEN** the setting is absent or blank, even if the request supplies a URL
- **THEN** the backend returns its `status` and `service_version` with `cli_version: null` without an upstream request or cache lookup

#### Scenario: Source changed
- **WHEN** the deployment switches from a `main/VERSION` URL to a `release/VERSION` URL
- **THEN** requests use only the latter source and cannot reuse the former source's cached value

### Requirement: Bounded retrieval of a semantic version
On a cache miss the backend SHALL make at most one GET, with two-second connect and read-inactivity timeouts, no redirect following and a 1024-byte body limit before trimming. Only a successful HTTP 200 body containing a single SemVer 2.0.0 value after whitespace trimming and removal of one optional lowercase `v` SHALL be accepted.

#### Scenario: Prerelease and build metadata are preserved
- **WHEN** the source returns `v1.2.3-rc.1+build.7` surrounded by whitespace
- **THEN** `cli_version` is `1.2.3-rc.1+build.7`

#### Scenario: No usable response
- **WHEN** the GET times out, redirects, returns a non-200 response, or yields empty, malformed or oversized content
- **THEN** the application returns `cli_version: null` without retrying or caching the failure

### Requirement: Shared one-hour freshness
API instances SHALL share valid versions for one hour from successful refresh, scoped to the full configured URL. Hits SHALL NOT extend expiry. After expiry the backend SHALL refresh on demand and SHALL NOT present the expired value when refresh fails.

#### Scenario: Shared fresh hit
- **WHEN** a second instance receives a request within one hour of a successful refresh for the same source
- **THEN** it returns the cached version without contacting the source

#### Scenario: Refresh fails and later recovers
- **WHEN** a cached value expires and the next lookup cannot obtain a valid version
- **THEN** that request returns `cli_version: null`; a subsequent request can fetch and publish a fresh valid version immediately

### Requirement: Independent health probes
`GET /health` SHALL retain its existing backend `status` and `version` response, without a `cli_version` field. It SHALL NOT read or write the CLI metadata cache, fetch the version source, or depend on the success of `GET /cli/status`.

#### Scenario: Probe while the version source is unavailable
- **WHEN** a probe calls `/health` with a configured but unreachable version source
- **THEN** it receives the usual `status: ok` and backend `version` without opening a cache session or making a CLI metadata fetch

#### Scenario: Probe while the metadata cache is unavailable
- **WHEN** the CLI metadata cache is unavailable
- **THEN** `/health` still returns its usual status and backend version without using it, and `/cli/status` returns the same backend fields with `cli_version: null`

### Requirement: Status ingress protection
With chart ingress rate limiting enabled, `GET /cli/status` SHALL select an explicit exact-path limiter ahead of the general CLI matcher and catch-all ingress. Its default allowance SHALL be 10 per minute per client, burst 5, IPv6 grouped by /64. Existing routes SHALL retain their limits, and rate limiting SHALL remain disabled by default.

#### Scenario: Anonymous requests exceed the allowance
- **WHEN** requests exceed the configured allowance on the exact status route
- **THEN** the edge returns HTTP 429 rather than falling through to the general CLI route or unprotected ingress

#### Scenario: Health and metadata have independent protection
- **WHEN** ingress rate limiting is enabled and the allowance for `GET /cli/status` is exhausted
- **THEN** `GET /health` still selects its existing limiter and does not consume or share the metadata route's allowance

#### Scenario: Other routes remain unchanged
- **WHEN** a request instead targets `POST /cli/connect`, another CLI route, or a non-CLI path
- **THEN** it selects the same existing protection or unprotected route as before
