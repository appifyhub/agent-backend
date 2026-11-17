# Tasks

## 1. Dependency

- [x] 1.1 Pin `replicate = "==2.0.0b4"` in `Pipfile`, relock, and verify `pipenv run pip show replicate` reports 2.0.0b4

## 2. Client and accounting (critical)

- [x] 2.1 Build the SDK client as `replicate.Replicate(bearer_token, timeout)` in `DI.base_replicate_client`; update `di_for_tests` and `test_di.py` to the 2.0 class and verify `pipenv run pytest test/di -q` passes
- [x] 2.2 Read `predict_time` by attribute in `ImageUsageStats.from_replicate_prediction`; update `stubs.external.replicate_prediction` / `replicate_file_output` to 2.0 models and verify `test_image_usage_stats.py` and `test_functions.py` pass
- [x] 2.3 Rework `PredictionUsageTrackingDecorator` to hold the predictions resource and current snapshot (wait/get/cancel by id) and `ReplicateUsageTrackingDecorator` to pass it; update `FakeReplicateClient` to the 2.0 resource API; verify every case in `test_replicate_usage_tracking_decorator.py` still asserts records, remote runtime, and balances, with the success case using output and metrics that appear only after completion and a null create version

## 3. Integration

- [x] 3.1 Run full offline pytest, repository-wide Ruff and spacing checks; all pass
- [x] 3.2 Run one live low-cost image generation through the production DI path in `scratchpad.py` and verify an image URL is returned and one usage record with remote runtime and cost is written (deduction itself is covered by decorator tests; the scratchpad payer uses its own Replicate key, so `uses_credits` is false)
