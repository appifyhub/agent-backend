## 1. Observability Deployment Handoff

- [x] 1.1 Wait for the user to confirm that `../charts/observability` has been published through the chart pipeline and installed directly with Helm, and that the OpenObserve UI and cluster Collector OTLP receiver are reachable
- [x] 1.2 Record the user-confirmed Collector service endpoint, OTLP protocol, deployment environment attributes, and SDK enablement contract needed by the separately managed backend deployment chart

## 2. OpenTelemetry Runtime

- [x] 2.1 Add explicit OpenTelemetry distribution, OTLP exporter, FastAPI, SQLAlchemy, logging, system-metrics, and supported HTTP-client instrumentation packages to `Pipfile` and update `Pipfile.lock`
- [x] 2.2 Wrap the production container entrypoint with an image-version-aware `opentelemetry-instrument` launcher, default the published image to `OTEL_SDK_DISABLED=true`, and preserve the existing local development command
- [x] 2.3 Configure bounded batch export defaults and verify that all destination, protocol, identity, environment, version, sampling, and enablement settings remain overridable through standard `OTEL_*` variables

## 3. Correlated Structured Logging

- [x] 3.1 Update `src/util/log.py` so non-local application events are emitted as one machine-parseable record containing stable severity, message, service identity, exception details, and valid active trace/span identifiers while local output remains readable
- [x] 3.2 Preserve secret scrubbing, existing log-level behavior, and the public `log.t/d/i/w/e` call surface without adding direct OTLP log export
- [x] 3.3 Record the user decision not to add a new logging test file; use focused offline smoke checks for the changed logging contract

## 4. Documentation and Offline Verification

- [x] 4.1 Document standard OpenTelemetry runtime variables, default-disabled image behavior, Collector dependency, and the boundary between automatic technical telemetry and explicit business metrics in the existing backend README
- [x] 4.2 Run focused offline smoke checks covering the changed startup and logging behavior, including startup with the SDK disabled and API health with an unreachable Collector
- [x] 4.3 Run `pipenv run ruff check --fix` and `pipenv run python tools/check_spacing.py --fix` on every changed Python file, then rerun the focused checks

## 5. Remote Image and Behavioral Verification

- [x] 5.1 Hand the completed source changes to the user for official image build and deployment through the existing remote pipeline; do not build or deploy a local image and do not mutate Helm or Kubernetes resources
- [x] 5.2 After the user deploys the official image and enables the SDK in the backend chart, exercise successful, controlled-error, database, and outbound HTTP paths
- [x] 5.3 Verify in the actual OpenObserve UI that request rate/latency/error metrics, process/runtime metrics, request and dependency traces, and correlated application error logs are present without duplicate log ingestion or sensitive values
