# Design

## Context

See `proposal.md` for motivation. Current state:

- `DI.base_replicate_client` builds `replicate.client.Client(api_token, timeout)`; `DI.replicate_client` wraps it in `ReplicateUsageTrackingDecorator`.
- `ReplicateUsageTrackingDecorator.predictions` proxies the SDK resource and intercepts only `create`: it runs `SpendingService.validate_pre_flight`, rolls back the DB session, calls the SDK, and returns a `PredictionUsageTrackingDecorator` around the 1.x `Prediction`.
- `PredictionUsageTrackingDecorator.wait()` relies on 1.x predictions being live objects: `prediction.wait()` and `prediction.reload()` mutate the same instance, and `prediction.cancel()` is a method. After waiting it reads `metrics["predict_time"]` through `ImageUsageStats.from_replicate_prediction`, then calls `UsageTrackingService.track_image_model` / `track_video_model` and `SpendingService.deduct`. Exceptions produce a failed record without deduction; the outcome is cached so repeated waits never double-charge.
- In 2.0, `Prediction` is a plain data model; `client.predictions.wait(prediction_id)`, `get(prediction_id = …)`, and `cancel(prediction_id = …)` return new snapshots. `metrics` is a `Metrics` model whose `predict_time` is an extra attribute, not a dict key. Responses are built without validation, which is what tolerates `version: null`.
- Tests replace the SDK client with `FakeReplicateClient` (registered in `di_for_tests` by SDK class) and build predictions through `stubs.external.replicate_prediction`.

## Goals / Non-Goals

**Goals:**

- Keep every accounting outcome identical: pre-flight before create, one record and one deduction on success, failed record without deduction on errors, video failure/timeout handling, and cached wait outcomes.
- Make the decorator track the terminal snapshot so both charging and result extraction see finished data.

**Non-Goals:**

- Changing image-wait semantics. As today, an image prediction that ends `failed` without raising is still tracked as successful by the decorator, and the generator then fails on the empty output. This is pre-existing behavior and stays unchanged here.
- Bounding image waits, retries, or any pricing change.

## Decisions

### D1. Pin `replicate==2.0.0b4`
Pre-releases need an exact pin; `~=` would not select them. Alternatives: `1.1.0b3` keeps the strict `version: str` (still crashes); raw HTTP bypass duplicates SDK transport and was rejected by the user.

### D2. The prediction decorator owns a predictions resource and a current snapshot
`PredictionUsageTrackingDecorator` receives the unwrapped `client.predictions` resource alongside the created snapshot. Image waits replace the snapshot with `predictions.wait(prediction_id = id)`; video polling replaces it with `predictions.get(prediction_id = id)` and cancels with `predictions.cancel(prediction_id = id)`. Usage stats and the `output`/`error`/`logs`/`status` properties always read the current snapshot. Without the swap, charging would read creation-time metrics and extraction would see no output after the user was already charged.

Alternative: one decorator-owned polling loop for images too. Rejected: it would change image-wait behavior (non-goal).

### D3. Read `predict_time` by attribute
`ImageUsageStats.from_replicate_prediction` reads `getattr(metrics, "predict_time", None)` and keeps the numeric check. Calling `.get` on the 2.0 model would raise after a successful generation, turning a billable success into a free failed record — the most important regression to guard.

### D4. Client construction
`replicate.Replicate(bearer_token = …, timeout = Timeout(…))`. The DI interceptor and `di_for_tests` key on this class.

### D5. Fake and stub follow the 2.0 resource API
`FakeReplicatePredictions` exposes `create(**kwargs)`, `get(prediction_id)`, `cancel(prediction_id)`, and `wait(prediction_id)` (the SDK's loop: get until terminal). `replicate_prediction` builds a 2.0 `Prediction` the way the SDK builds responses (unvalidated construction), with required 2.0 fields defaulted, so a null version is representable. `replicate_file_output` uses the 2.0 `FileOutput`.

## Risks / Trade-offs

- [Beta SDK in production] → exact pin; covered by decorator tests plus a live scratchpad generation before release.
- [Silent accounting regression] → decorator tests assert records, remote runtime, and balances for success, failure, video failure, and timeout against real repositories.
- [Image predictions with `failed` status are charged] → pre-existing, documented in Non-Goals; flagged to the user.

## Migration Plan

Ship with the lock update. Rollback is reverting the commit; no data or schema changes.
