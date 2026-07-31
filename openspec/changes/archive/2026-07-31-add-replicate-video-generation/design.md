## Context

Image generation already establishes the main product conventions this change should preserve: external model definitions and per-purpose user selections, copywriter-assisted prompts, normalized `1K`/`2K`/`4K` sizes, closest-ratio mapping, credit preflight and usage tracking, generated attachment persistence, and smart platform delivery. Video differs in three important ways:

1. Replicate predictions can take minutes, so the chat request must finish before generation and delivery.
2. Telegram and WhatsApp require native video APIs and platform-specific preparation; the existing photo/document paths are not sufficient.
3. Video prices depend on generated duration as well as resolution, and Ray's published 5- and 10-second prices yield different per-second rates.

The service runs as a Debian Linux x86 Docker image with approximately 1 GB RAM per instance, developers use macOS ARM, and CI runs on GitHub-hosted Ubuntu. Replicate is the only video provider in this change. The supplied model documentation is retained under `docs/replicate-video-docs/`.

The implementation crosses external tool configuration, user persistence, accounting, prompt construction, Replicate SDK usage, attachment handling, Telegram and WhatsApp models/APIs/SDKs, DI, API documentation, database migration, runtime packaging, and CI. Implementation therefore proceeds from data contracts outward, with an explicit user review gate after every milestone.

## Goals / Non-Goals

**Goals:**

- Provide one understandable video-generation tool and one user-selected Replicate video model for both text-only and reference-image-conditioned generation.
- Support ordered attachment IDs and external URLs, including multiple references where the selected model supports them and deterministic first-image fallback where it does not.
- Normalize duration, resolution, and aspect ratio across all six initial Replicate model definitions without returning unsupported-option failures.
- Estimate, preflight, record, and deduct video usage in credits, where one credit is one US dollar cent.
- Return promptly from chat while a bounded, timed background worker completes generation and sends the eventual result.
- Deliver generated videos natively through Telegram and WhatsApp, converting and reducing provider outputs only when needed.
- Correctly classify and ingest inbound video on both platforms.
- Keep the media pipeline portable across Linux x86, macOS ARM, and GitHub-hosted Ubuntu.

**Non-Goals:**

- Video-to-video editing, video extension, or input videos.
- Last-frame controls, input audio, multiple video references, intelligent/exact duration, HDR, EXR export, looping, or draft-quality controls.
- A video provider other than Replicate.
- Durable background jobs, cross-instance queues, webhooks, restart recovery, retries after process death, or progress updates after the initial acknowledgement.
- Video understanding, frame extraction for vision analysis, or video transcription.
- Changing existing image generation or image accounting behavior except where a shared additive contract requires it.

## Decisions

### 1. Use one tool purpose and one optional-reference LLM function

Add `ToolType.videos_gen`, `tool_choice_videos_gen`, and one `generate_video` function:

```text
prompt
attachment_ids                (optional comma-separated string)
urls                          (optional comma-separated string)
duration                      (optional short/medium/long)
aspect_ratio                  (optional normalized ratio)
size                          (optional 1K/2K/4K)
```

No references selects text-to-video. One or more references selects image-conditioned generation. This differs usefully from image editing: every operation still creates a new video through the same selected generator model, and all targeted models support both modes. A separate image-to-video purpose would duplicate user selection, migrations, profile fields, resolver branches, and LLM instructions without enabling an independently meaningful provider choice.

The tool follows the existing `process_media` convention of comma-separated attachment IDs and URLs. `ChatAttachmentService.resolve_attachments` remains the authority for local IDs and external URL normalization. The resolved order is deterministic. The model definition describes its maximum reference count:

- an array-capable adapter receives the first supported subset;
- a single-image adapter receives only the first image;
- details report how many references were used and ignored;
- a singular resolved image supplies the source ratio when no explicit ratio is requested.

Alternative considered: separate text-to-video and image-to-video tool purposes and functions. Rejected because the selected models and user intent form one generation capability, while a single explicit optional-reference contract is simpler and now preferred.

### 2. Extend existing contracts before adding orchestration

The first implementation layer adds:

- `ToolType.videos_gen`;
- nullable `tool_choice_videos_gen` across user domain, DB, repositories, mappers, API payloads/responses, profile merge, sponsorship, system agents, intelligence presets, and documentation;
- `output_video_1k_second`, `output_video_2k_second`, and `output_video_4k_second` on `CostEstimate`;
- output video size and duration fields on usage domain, DB, repositories, mappers, and API representations;
- Replicate provider capability labels and model catalog entries.

The user will run `./tools/db_generate_migration -y` after model changes. The generated migration is reviewed before any later milestone proceeds. Historical migrations remain immutable, and migration logic uses literal persisted strings rather than runtime model definitions.

Alternative considered: defer persistence until the generator is connected. Rejected because inward-to-outward implementation and review require the data contract to stabilize first.

### 3. Keep the video parameter utility as simple as the image utility

`video_api_utils` is a separate sibling of `image_api_utils`, not a capability framework. It returns one readable `UnifiedVideoParameters` value containing the prompt, mapped duration seconds, actual normalized output size, provider resolution, aspect ratio, mutually exclusive `image`/`start_image`/`reference_images` inputs, and the few supported provider defaults.

The LLM-facing duration, size, and aspect-ratio inputs are optional and default to `None`, matching the image-tool contract. The utility resolves an omitted duration to the selected model's `medium` duration and an omitted size to `1K`; the returned normalized size reflects any model clamp for accounting while `resolution` contains the Replicate input value. The aspect-ratio resolver returns the final provider-ready value: an explicit aspect ratio is preserved when supported and otherwise uses the existing image closest-ratio helper; omitted ratios use the provider's native input-image behavior when references are present and `16:9` otherwise.

Reference attachment-ID and external-URL resolution occurs when the final generator has chat access. The utility receives the resolved public URLs and preserves their order. One URL becomes the model's singular `image` or `start_image`. With multiple URLs, an array-capable model receives the first supported subset as `reference_images`, while a singular model receives only the first URL through its singular field. Incompatible singular-image and reference-image inputs are never populated together. It does not open files or calculate image geometry.

As in the image path, a small model-specific allowlist removes the internal normalized size and every irrelevant optional field before the dictionary is sent to Replicate. Callers do not remap duration, resolution, references, aspect ratio, safety, prompt upsampling, or audio settings.

Duration mappings are:

| Model | Text short/medium/long | With references short/medium/long |
|---|---|---|
| P-Video | 4 / 5 / 10 | 4 / 5 / 10 |
| Seedance 2.0 | 4 / 5 / 10 | 4 / 5 / 10 |
| Seedance 2.0 Fast | 4 / 5 / 10 | 4 / 5 / 10 |
| Veo 3.1 | 4 / 6 / 8 | 4 / 6 / 8 |
| Veo 3.1 Fast | 4 / 6 / 8 | 4 / 6 / 8 |
| Ray 3.2 | 5 / 5 / 10 | 5 / 5 / 5 |

Ray's reference-image long tier is 5 seconds because its schema forbids 10 seconds with `start_image`; Ray text-only long uses 10 seconds with HDR off.

User-facing resolution mappings are:

| Tier | Product resolution | P-Video | Seedance | Seedance Fast | Veo | Ray |
|---|---|---|---|---|---|---|
| 1K | 720p | 720p | 720p | 720p | 720p | 720p |
| 2K | 1080p | 1080p | 1080p | 720p | 1080p | 1080p |
| 4K | 2160p/4K | 1080p | `4k` | 720p | 1080p | 1080p |

The naming intentionally follows the existing image product vocabulary rather than introducing `0.7K`.

The accepted ratio union is `9:16`, `2:3`, `3:4`, `1:1`, `4:3`, `3:2`, `16:9`, and `21:9`.

Alternative considered: expose only the intersection of model capabilities. Rejected because it would unnecessarily reduce capable models and make model switching less useful.

### 4. Keep provider differences explicit in the parameter utility

The parameter utility uses direct model branches that remain readable beside the image utility:

- P-Video uses its single `image` input, 24 FPS, `draft=false`, generated audio, `disable_safety_filter=true`, and provider prompt upsampling disabled.
- Seedance uses `image` for one first-frame reference and its documented reference-image array when multiple references select that mode; it maps to a documented concrete ratio and enables generated audio.
- Veo maps one image or its supported reference-image collection, limits aspect ratio to landscape/portrait, and enables generated audio.
- Ray uses the first image as `start_image`, omits ratio for an anchor image, disables HDR/EXR/loop/end-image behavior, and treats output as silent.

Safety filtering is disabled only through documented provider parameters. P-Video currently exposes the relevant switch; unsupported fields are never invented for other schemas.

Video inputs and editing-oriented Seedance parameters are not mapped, even though the provider exposes them. This preserves the option to add editing in a later change without implicitly supporting it now.

### 5. Add a screenwriter variant inside the final generator

Add a video-specific prompt fragment/resolver and invoke it directly inside the final video generator, matching how `SmartImageGenerator` performs image prompt upscaling as part of generation. The generator uses the existing `ToolType.copywriting` configured model and improves motion, shot composition, camera movement, pacing, continuity, lighting, audio cues, and quoted dialogue while preserving the request. No standalone screenwriter service is introduced.

The screenwriter prompt fragment receives the post-truncation reference-image count. When that count is non-zero, it uses the fact that the video model will receive references to make the prompt clearly image-conditioned where helpful, without claiming the screenwriter can inspect or describe unseen visual details. Text-only requests pass zero. Prompt enhancement runs synchronously through the request DI, matching `SmartImageGenerator`; only provider generation and delivery move to the background worker.

Provider prompt enhancement is disabled where configurable to avoid double rewriting. No persisted `screenwriter` tool purpose is introduced.

Alternative considered: use provider prompt upsampling only. Rejected because application-side screenwriting is consistent across models and remains under product control.

### 6. Use cent-per-generated-second cost fields

One credit equals one US dollar cent. `CostEstimate` adds:

```text
output_video_1k_second
output_video_2k_second
output_video_4k_second
```

`get_minimum_for` gains mapped output video size and duration inputs and multiplies the rate by generated seconds. Both preflight and successful usage accounting use the same mapped parameters:

| Model | 1K credits/s | 2K credits/s | 4K credits/s |
|---|---:|---:|---:|
| P-Video | 2 | 4 | 4 |
| Seedance 2.0 non-video input | 18 | 45 | 100 |
| Seedance 2.0 Fast non-video input | 15 | 15 | 15 |
| Veo 3.1 Fast with audio | 15 | 15 | 15 |
| Veo 3.1 with audio | 40 | 40 | 40 |
| Ray 3.2 SDR average | 15 | 50 | 50 |

Seedance text and image inputs use `non_video_in`; the supplied `video_in` rates remain unused because input video is out of scope. Ray uses the requested arithmetic mean of the published 5- and 10-second per-second rates, deliberately overestimating 5 seconds and underestimating 10 seconds instead of adding a duration override structure.

Add `track_video_model` and corresponding usage fields rather than misusing `second_of_runtime`, which represents provider compute duration. Successful output deduction occurs after confirming `prediction.status == "succeeded"`. Failed, canceled, and timed-out predictions use failed tracking without successful-output deduction. `SimpleVideoGenerator` extracts the output URL after the decorated wait and accounting, matching the existing Replicate image flow.

The background worker constructs its own detached DI and uses the existing Replicate client and prediction decorators, preserving the same preflight and terminal accounting path used for images. Immediately after prediction creation, it rolls back the detached SQLAlchemy session before waiting. This keeps the DI, decorator, and session object available for terminal accounting while releasing the active transaction and checked-out connection during the long poll. Terminal tracking then lazily checks out a connection through the same session. After accounting, the worker rolls back once more and reuses that DI for persistence and delivery before closing the context.

Alternative considered: exact cost matrices by size and duration. Rejected in favor of the requested per-second fields and averaged Ray rates.

### 7. Bound background work and poll with a real deadline

The LLM tool performs input validation, reference resolution, parameter mapping, tool resolution, credit preflight, and synchronous screenwriter prompt enhancement through the request DI. It then acquires a non-blocking process-local `BoundedSemaphore(16)`, launches a daemon thread, and immediately returns a structured result instructing the chat model to acknowledge that generation started. Screenwriting failures occur before admission and therefore require no worker-slot cleanup; failures after admission release the slot.

The worker captures stable values rather than request services: invoker ID, chat ID, configured tool data, normalized parameters containing any public reference URLs, and delivery context.

```text
request DI
  -> validate, resolve, preflight
  -> screenwriter prompt enhancement
  -> acquire job slot
  -> start daemon worker
  -> return generating JSON
  -> final chat acknowledgement and notifier stop

worker
  -> background-owned detached DI: credential resolution
  -> decorated Replicate SDK: preflight and create prediction
  -> rollback detached DB session
  -> decorated prediction.wait(): poll prediction.reload() with monotonic 600-second deadline
  -> cancel unfinished prediction at deadline
  -> terminal accounting reuses the decorator and lazily reacquires a DB connection
  -> rollback detached DB session again
  -> same background DI: archive, prepare, and send
  -> close background DI/session context
  -> fresh detached DI only when a failure must be announced
  -> release job slot in finally
```

The installed Replicate SDK's raw `Prediction.wait()` has no timeout. The existing prediction decorator therefore adds a bounded video wait that polls terminal states with `prediction.reload()` and uses `prediction.cancel()` at the deadline. Each HTTP operation retains a normal request timeout in addition to the total deadline.

The worker never retains the request-scoped database session. Its background-owned detached session object remains available during polling, but `rollback_db_session()` ensures that no active transaction or checked-out connection remains between prediction creation and terminal accounting.

Failure notification preserves an existing structured `ServiceError` and wraps an unexpected exception in `ExternalServiceError` with the video-generation error code. The system-announcement copywriter receives a directly user-addressed failure message followed by the sanitized formatted error details, then translates and presents that message naturally for the target chat.

Alternative considered: Replicate webhooks plus a durable job table. Rejected for this change because the existing SDK is sufficient and the requested design accepts best-effort in-process delivery.

### 8. Separate cheap polling concurrency from expensive preparation concurrency

Sixteen admitted jobs are acceptable on a 1 GB service instance because prediction threads mostly sleep and do not retain active DB transactions, checked-out connections, or video bodies. A second process-local `BoundedSemaphore(2)` protects video download, FFprobe, FFmpeg, archival conversion, and native delivery preparation.

Remote output streams into a temporary file. Waiting jobs do not download their video before acquiring the preparation slot. FFprobe and FFmpeg run through `subprocess` with a 300-second timeout, explicit termination, and `finally` cleanup.

The 17th job receives a structured busy response rather than risking an OOM restart that would lose every in-flight best-effort job.

Alternative considered: four total worker threads. Rejected as unnecessarily restrictive for sleeping pollers. Alternative considered: no bound. Rejected because simultaneous completions and transcodes can exhaust a 1 GB instance.

### 9. Use system FFmpeg instead of native Python media bindings

Add a small video inspection/preparation wrapper around `ffprobe` and `ffmpeg`. It checks executable availability and raises a structured configuration error when missing.

- Debian Linux x86 production continues to use the existing `apt` FFmpeg package in the Docker image.
- macOS ARM development uses the developer's native Homebrew FFmpeg.
- GitHub-hosted Ubuntu installs or verifies FFmpeg before offline media tests.

No PyAV or bundled architecture-specific binary dependency is introduced. Command construction and parsing remain identical across architectures.

Preparation first inspects the source. A compliant file is reused. Otherwise it creates MP4/H.264, optional AAC, `yuv420p`, and fast-start output. For byte-limit failures, it calculates a duration-aware target bitrate, retries with a lower bitrate or resolution, and verifies the result.

### 10. Add explicit native video APIs and smart SDK behavior

`PlatformBotSDK` adds `send_video` and `smart_send_video`; Telegram and WhatsApp implement their low-level API and persistence behavior.

Video preparation lives in `PlatformBotSDK.prepare_outgoing_video_attachment` beside the existing photo/document preparation method. It downloads, normalizes, and stores one outbound attachment for `send_video`. `smart_send_video` mirrors `smart_send_photo` exactly: photo mode tries native delivery and falls back to the existing document sender, file mode uses the document sender, and all mode attempts both. Telegram and WhatsApp SDKs contain only their native video and document delivery implementations.

Telegram:

- native mode uses multipart `sendVideo` with prepared MP4;
- file mode uses multipart `sendDocument` with the original MP4;
- all mode sends both;
- the attachment-storage abstraction copies stored bytes into an auto-deleted temporary file immediately before Telegram multipart upload;
- multipart avoids Telegram's lower URL-fetch limit and unreliable MP4 document URL behavior.

WhatsApp:

- native mode sends a prepared MP4/3GP with H.264, at most one AAC stream, and at most 16 MB;
- file mode sends the archived original as a document through its attachment public URL;
- all mode sends the prepared native video and the original document;
- document delivery includes the attachment filename.

Each selected delivery path prepares and stores exactly the attachment it sends, following photo delivery. Native mode stores the prepared video, document mode stores the unresized source, and all mode performs both independent sends.

Alternative considered: send every provider URL directly. Rejected because provider outputs can violate codecs, containers, sizes, URL-fetch limits, and user media preferences.

### 11. Make inbound video a first-class attachment category

Move `video/mp4`, `video/mpeg`, and `video/webm` out of audio classification into dedicated video formats. The generic attachment processor reports unsupported video analysis rather than sending MP4 into transcription.

WhatsApp already represents inbound video and retains its low-level authenticated media download. Add Telegram `Video` and `Message.video` API models, map caption and metadata, preserve a null MIME type when Telegram omits it, and reuse `TelegramBotAPI` file download. Platform download errors continue through the existing structured external-service flow.

Video ingestion does not imply video understanding or editing.

### 12. Enforce milestone review gates operationally

`tasks.md` orders work from domain and persistence outward. Every milestone ends with an unchecked `REVIEW GATE` task requiring the implementer to:

1. stop all implementation;
2. present the milestone diff, focused tests, lint, spacing, and migration evidence where applicable;
3. wait for explicit user approval;
4. mark the gate complete only after that approval.

The next milestone must never start in the same autonomous run before approval.

## Risks / Trade-offs

- **Process restart loses in-flight jobs** → Treat the worker as explicitly best-effort, send terminal failures when the process remains alive, and leave durable jobs/webhooks for a later change.
- **Sixteen jobs finish simultaneously** → Allow sixteen cheap pollers but only two preparation/download/transcode sections; stream to disk and release both semaphores in `finally`.
- **Replicate cancellation fails at the deadline** → Stop local polling regardless, log cancellation failure, record failed usage without deduction, notify the partner, and release the worker.
- **User funds or model selection change while a job runs** → Capture the admitted configured tool, payer, mapped parameters, and durable references; perform preflight before creation and bill the admitted configuration at completion.
- **A model changes its schema or pricing** → Keep model-specific parameter filters and cost fields in the catalog with focused mapping tests; do not guess missing prices.
- **Ray average pricing differs from actual per-output cost** → Document the intentional smoothing and use the agreed arithmetic mean consistently in preflight and deduction.
- **Multiple references change provider semantics** → Keep provider-specific mapping explicit, preserve first-reference ordering, cap inputs deterministically, and report used/ignored counts.
- **WhatsApp document support changes** → Keep native/document preference behavior inside the WhatsApp SDK and retain the manually verified public-URL document path.
- **Repeated transcoding degrades quality** → Preserve compliant outputs and transcode only for platform compatibility or byte limits.
- **FFmpeg behavior differs by platform/version** → Use stable command-line options, machine-readable FFprobe JSON, native package managers, offline fixtures, and Docker/Ubuntu validation.
- **Telegram or WhatsApp limits change** → Centralize platform constraints in preparation policy and low-level API tests so changes remain localized.
- **Database migration introduces selection or usage drift** → Generate through the repository tool, inspect the migration before proceeding, use literal persisted values, and validate upgrade/downgrade SQL as appropriate.

## Migration Plan

1. Add nullable video tool-choice and usage columns through model changes.
2. Ask the user to run `./tools/db_generate_migration -y`; inspect the generated migration, confirm Alembic imports and head state, and obtain milestone approval.
3. Deploy additive domain/API support while the nullable selection falls back to the intelligence-preset Seedance 2.0 agent-choice default; use P-Video for lowest-price and Ray 3.2 for highest-price.
4. Add media preparation and platform video APIs/SDKs before exposing the LLM tool.
5. Add and validate Replicate model definitions and adapters.
6. Connect the final generator and LLM tool only after all inner layers are reviewed.
7. Rollback application code by disabling/removing the unexposed generator path; nullable additive columns may remain safely if a database downgrade is not appropriate.

## Open Questions

None. The required provider schemas, Seedance Fast 720p pricing, credit unit, concurrency limits, deadlines, reference behavior, platform fallback, and milestone-review policy are resolved for proposal scope.
