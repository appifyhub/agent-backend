## Context

See `proposal.md` for motivation and `specs/application-observability/spec.md` for the behavioral contract.

The backend is a Python 3.12 FastAPI process launched from the container through `pipenv run python src/main.py`. It uses SQLAlchemy plus several synchronous and asynchronous HTTP clients. Application logging is centralized in `src/util/log.py`, writes through Uvicorn outside local development, and already scrubs configured secrets from rendered messages. There is currently no metrics, tracing, or OpenTelemetry dependency.

The observability backend is managed separately in the sibling charts repository. This repo-local change cannot edit or deploy that repository. The agreed external architecture is an in-cluster OpenObserve release backed by a dedicated database/role on the existing CloudNativePG cluster and a dedicated bucket on the existing SeaweedFS S3 service, plus an ephemeral NATS coordinator and node and cluster OpenTelemetry Collectors. It uses no new durable PVC and no node-placement constraints.

## Goals / Non-Goals

**Goals:**

- Produce portable OTLP traces and metrics using standard OpenTelemetry configuration.
- Cover inbound FastAPI requests, SQLAlchemy operations, supported outbound HTTP clients, Python process/runtime health, and exceptions.
- Make application stdout logs searchable by severity and correlatable with active traces.
- Keep telemetry overhead bounded and independent from request success.
- Preserve a simple backend switch: repoint standard OTLP configuration rather than re-instrument application code.

**Non-Goals:**

- Deploying, upgrading, or deleting Kubernetes resources from this repository's OpenSpec apply phase.
- Managing the OpenObserve, PostgreSQL, SeaweedFS, Traefik, Doppler, or Collector chart resources.
- Sending application logs directly over OTLP; the node Collector remains responsible for stdout log collection.
- Adding distributed tracing to third-party systems that do not propagate OpenTelemetry context.
- Continuous profiling, Kubernetes cost allocation, energy metrics, or Grafana compatibility.
- Defining product/business counters such as credits, LLM tokens, or active users. Those require separate semantic decisions; this change provides technical request and runtime usage telemetry.

## Decisions

### Use Python auto-instrumentation with explicit locked packages

Install `opentelemetry-distro`, the OTLP exporter, and explicit instrumentation packages for FastAPI, SQLAlchemy, logging, system metrics, and the HTTP client libraries present in the application. Launch the production process through a lightweight image entrypoint that reads the application version from `pyproject.toml`, adds it to the OpenTelemetry resource as `service.version`, and then executes `opentelemetry-instrument` before `src/main.py` imports the application.

Explicit dependencies are preferred over running `opentelemetry-bootstrap --action=install` during image construction: Pipenv remains the dependency source of truth, `Pipfile.lock` pins the exact compatible set, and production images remain reproducible. Direct SDK initialization in application modules is rejected because it duplicates standard environment configuration and couples imports to process startup order.

The standard `OTEL_SDK_DISABLED` switch preserves local and emergency operation without a second application entrypoint.
The published image defaults the standard SDK-disable switch to true so self-hosters without a Collector do not generate export failures. The separately managed deployment chart explicitly enables the SDK only when it also supplies a valid Collector endpoint. This preserves mandatory telemetry in the managed environments without making an external service a hidden requirement for running the image.

### Export application signals to the singleton cluster Collector

The live application export contract is OTLP HTTP/protobuf at `http://otel-cluster.observability.svc.cluster.local:4318`. Managed deployments set `OTEL_EXPORTER_OTLP_ENDPOINT` to that URL, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SERVICE_NAME=the-agent`, `OTEL_RESOURCE_ATTRIBUTES` with `deployment.environment.name`, and `OTEL_SDK_DISABLED=false`. The image entrypoint derives `service.version` from its own `pyproject.toml`, so digest-based image updates report the new version without requiring a deployment configuration change.

The application exports to the Collector service supplied by the external observability release, not directly to OpenObserve. This keeps destination credentials and topology out of application configuration, centralizes retry and backend routing, and permits replacing OpenObserve by changing the Collector exporter. Direct-to-OpenObserve export is simpler by one hop but gives every application knowledge of the storage backend and makes future routing changes harder.

At the current low traffic level, traces use parent-based always-on sampling so errors are not accidentally omitted by probabilistic head sampling. Sampling can move to the Collector if volume later justifies it. Metrics use a conservative periodic export interval rather than per-request network writes.

### Keep logs on stdout and add structured correlation fields

`src/util/log.py` remains the sole application logging facade. Non-local logging emits one machine-parseable record per event with at least timestamp, severity, message, logger/service identity, and exception details; when OpenTelemetry context is valid, it also emits trace and span IDs. Local development retains readable console output.

The OpenTelemetry logging instrumentation injects active context into Python `LogRecord` objects, while the application's formatter controls the stable stdout representation. The formatter continues applying the existing secret scrubber before output. Direct OTLP log export is disabled to avoid duplicate records because the node Collector already tails container stdout.

Structured single-record exceptions are preferred over the current multiple multiline records because operators need one searchable event with reliable severity and correlation fields. Existing callers of `log.t/d/i/w/e` retain their API.

### Rely on standard framework semantic conventions and bound cardinality

Framework instrumentation supplies route templates, HTTP method/status/duration, database operation metadata, and client destinations. Configuration must not enable request/response bodies or sensitive headers. Metrics use matched route templates rather than raw URL paths; dynamic user IDs, chat IDs, request IDs, exception messages, and database statements are not metric labels.

The application resource includes service name, service version, and deployment environment so staging and production remain separable without inventing proprietary fields.

### Treat collector failure as telemetry loss, never application failure

The SDK uses batch processors, short exporter timeouts, and bounded queues. Export errors remain diagnostics and must not escape into request handling. The application does not synchronously flush on every request. Normal graceful shutdown may attempt a bounded flush, but shutdown cannot wait indefinitely for an unavailable Collector.

No fallback file, local database, or retry service is added. Such fallbacks would consume pod disk and turn an observability outage into application resource pressure.

### Gate backend rollout on the user-managed observability chart

Work proceeds in two explicitly separated phases:

1. Outside this OpenSpec apply scope, create `../charts/observability` as a convention-matching wrapper around pinned official OpenObserve and OpenTelemetry Collector charts. The user publishes it through the normal chart pipeline and deploys the cluster-level release directly with Helm; no local Helm apply or Kubernetes mutation is performed by the implementation agent.
2. Only after the user confirms the official images are running and supplies the cluster Collector service contract does backend instrumentation proceed. The backend image is then built and deployed through the existing remote pipeline, never from a local image.

The sibling `the-agent-api` chart will need standard `OTEL_*` environment and startup configuration, but those edits remain outside this repo-local OpenSpec change and follow the same user-controlled deployment boundary.

## Risks / Trade-offs

- **[Auto-instrumentation package incompatibility]** → Lock the complete OpenTelemetry package set together and run a real application smoke test against a local/no-op or dry-run-compatible endpoint before publishing an image.
- **[Collector outage creates retry overhead]** → Use batch export, bounded queues, short timeouts, and validate that the API remains healthy with an unreachable endpoint.
- **[Telemetry leaks sensitive input]** → Keep bodies and headers disabled, retain secret scrubbing, constrain attributes to semantic-convention fields, and test representative authenticated/error paths.
- **[High-cardinality metrics reproduce the previous quota problem]** → Use framework route templates and forbid user/request/error values as metric attributes. The self-hosted destination has no vendor series quota, but unbounded dimensions would still waste storage and memory.
- **[Changing production log shape affects ad hoc consumers]** → Keep local output unchanged, document the production JSON schema, and verify the node Collector parses both application JSON and ordinary Uvicorn/container records.
- **[Always-on traces grow storage]** → Current traffic is intentionally small; apply finite retention in OpenObserve and move sampling to the Collector if measured storage growth warrants it.
- **[In-cluster monitoring is unavailable during cluster-wide failure]** → Accepted for cost and operational simplicity; this design does not claim external outage visibility.
- **[Transient OpenObserve WAL or NATS messages can be lost without a PVC]** → Accepted for this workload; PostgreSQL stores metadata and SeaweedFS stores flushed telemetry. NATS uses ephemeral file storage, bounded by the pod's Kubernetes ephemeral-storage limit, for coordination and internal queueing. Tune flush intervals in the external chart to bound the loss window.

## Migration Plan

1. Complete and document `../charts/observability`, including PostgreSQL metadata, SeaweedFS object storage, ephemeral NATS coordination, Collector topology, ingress, secrets, retention, dashboards, and resource settings.
2. The user removes Grafana resources and installs the observability chart directly with Helm, then confirms OpenObserve UI and Collector OTLP readiness.
3. Add and lock backend OpenTelemetry dependencies, startup wrapping, and correlated structured logging.
4. Validate observable contracts offline where possible, then build the official backend image through the existing remote pipeline.
5. Update the separately managed backend deployment chart with the agreed Collector endpoint and standard resource attributes; the user deploys it.
6. Exercise health, successful request, controlled error, database, and outbound HTTP paths and verify traces, metrics, and correlated error logs in OpenObserve.

Rollback is configuration-first: set `OTEL_SDK_DISABLED=true` to stop SDK activity without changing the image. If logging or startup behavior is implicated, restore the previous backend image through the existing deployment process. There is no application database migration to reverse, and the observability chart can remain deployed while backend telemetry is disabled.
