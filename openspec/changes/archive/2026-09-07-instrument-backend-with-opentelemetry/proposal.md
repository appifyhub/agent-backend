## Why

The backend currently emits only uncorrelated stdout logs, so operators cannot reliably connect application errors to requests, database work, or outbound calls in the replacement observability UI. Standard OpenTelemetry instrumentation is needed now to make backend health and failures directly observable without coupling the application to a specific monitoring vendor.

## What Changes

- Add standard OpenTelemetry SDK, OTLP exporter, and instrumentation packages for FastAPI, SQLAlchemy, and supported outbound HTTP clients.
- Start the backend through OpenTelemetry's Python auto-instrumentation and export traces and runtime/request metrics through OTLP.
- Attach service, environment, and deployment resource attributes using standard OpenTelemetry configuration.
- Correlate structured application logs with the active trace and span so operators can navigate between errors, requests, and dependency activity.
- Keep telemetry non-blocking: an unavailable collector must not prevent the API from starting or serving requests.
- Document the required runtime environment and the boundary between automatic technical telemetry and explicit business-usage metrics.

## Capabilities

### New Capabilities

- `application-observability`: Standardized application telemetry covering request health, exceptions, database activity, outbound dependencies, and log-to-trace correlation.

### Modified Capabilities

None.

## Impact

- Affected code: application startup, dependency definitions, runtime configuration, and logging context.
- New dependencies: OpenTelemetry Python SDK, OTLP exporter, distribution/auto-instrumentation support, and integrations for the frameworks actually used by the backend.
- Runtime contract: the deployment supplies a reachable OTLP endpoint plus standard `OTEL_*` resource and exporter settings.
- External dependency: the separately managed `../charts/observability` release must be deployed and expose its cluster collector before end-to-end verification. Deployment-chart work remains outside this repository's OpenSpec apply scope.
- No public HTTP API or database schema changes.
