# Proposal

## Why

Replicate's prediction-create response now carries `version: null`. The pinned `replicate` 1.0.7 SDK validates `Prediction.version` as a required string and raises `ValidationError` while parsing that response, so every Replicate image and video generation fails after Replicate has already started (and bills) the prediction. Reproduced in production at 2026-11-16 23:53Z (GPT Image 2.6 Flare) and again via the scratchpad with Nano Banana Pro on both `version =` and `model =`. No stable 1.x release fixes it; `1.1.0b3` keeps the required field, while `2.0.0b4` builds responses without strict validation and was verified live (create returned `version=None`, `wait` returned `hidden`/`succeeded`).

## What Changes

- Pin `replicate` to `2.0.0b4` (a pre-release, so an exact pin is required) and refresh `Pipfile.lock`.
- Construct the SDK client the 2.0 way (`Replicate(bearer_token = …)`) in the DI provider.
- Rework the usage-tracking decorator around the 2.0 resource model: waiting, polling, and cancelling go through `client.predictions` by id, because 2.0 predictions are plain data models without `wait`/`reload`/`cancel`.
- Read `predict_time` from the 2.0 metrics model instead of a dict.
- Update the Replicate fake, the prediction stub, and the existing tests that exercise them to the 2.0 shapes. No new test files.
- **BREAKING** (internal only): `replicate.client` and `replicate.prediction` no longer exist; nothing outside Replicate integration code imports them.

## Capabilities

### New Capabilities

- `replicate-generation`: how Replicate-backed image and video generation behaves from the caller's point of view — tolerance of a missing version at creation, result extraction, bounded video waits, and usage accounting.

### Modified Capabilities

<!-- none: openspec/specs is empty -->

## Impact

- Code: `Pipfile`, `Pipfile.lock`, `src/di/di.py`, `src/features/accounting/usage/decorators/replicate_usage_tracking_decorator.py`, `src/features/accounting/usage/image_usage_stats.py`; `simple_image_generator.py` / `simple_video_generator.py` keep their call shape.
- Tests: `test/fakes/fake_replicate_client.py`, `test/stubs/external.py`, `test/util/di_utils.py`, and the decorator, usage-stats, `test_functions`, and smart-video-generator tests.
- Dependency risk: production runs a beta SDK until a stable 2.x ships.
- No API, database, pricing, or model-catalog change.
