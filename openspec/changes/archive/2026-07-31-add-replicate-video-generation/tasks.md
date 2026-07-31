## 1. Domain contracts, persistence, and catalog

- [x] 1.1 Inspect the nearest existing tests for every affected layer and obtain explicit user approval for the complete list of any new test files before creating them. No new test files are needed for Section 1; existing modules cover its layers.
- [x] 1.2 Add `ToolType.videos_gen`, `CostEstimate.output_video_1k_second`, `output_video_2k_second`, and `output_video_4k_second`, plus mapped video size/duration inputs in minimum-cost calculation.
- [x] 1.3 Add output video size and duration fields to the usage domain, DB model, repository mapper, API mapper, and usage response schema.
- [x] 1.4 Add nullable `tool_choice_videos_gen` through the user domain and DB models, repositories, mappers, update payloads, responses, profile merge, sponsorship, system-agent configuration, and intelligence presets.
- [x] 1.5 Add all six Replicate video definitions and cent-per-second prices to the external tool catalog, advertise video generation on the Replicate provider, and assign P-Video, Ray 3.2, and Seedance 2.0 to the lowest-price, highest-price, and agent-choice presets respectively.
- [x] 1.6 Update API documentation for the video tool selection, model exposure, and usage metadata.
- [x] 1.7 Add or update focused offline tests for cost units, user persistence/mapping, tool resolution, provider exposure, preset fallback, sponsorship, and usage serialization.
- [x] 1.8 Ask the user to run `./tools/db_generate_migration -y`; inspect the generated migration, verify `src/db/alembic/env.py` imports, literal persisted values, upgrade/downgrade behavior, and the single Alembic head.
- [x] 1.9 Run Ruff and the spacing checker on changed Python files, run the focused Section 1 tests, and run `git diff --check`.
- [x] 1.10 **REVIEW GATE — STOP. Present the Section 1 diff, migration, and validation evidence. Do not mark this task complete or begin Section 2 until the user explicitly approves.**

## 2. Core video policies and screenwriter

- [x] 2.1 Add a video-specific unified parameter value, mirroring image parameter utility readability, for semantic duration, normalized size, aspect ratio, and ordered reference URLs.
- [x] 2.2 Map optional `short`/`medium`/`long` input directly to model- and mode-supported duration seconds with a `medium` default.
- [x] 2.3 Normalize optional `1K`/`2K`/`4K` input with a `1K` default, map provider resolution, and retain the actual clamped tier for accounting.
- [x] 2.4 Implement the complete ratio union, a `16:9` no-image default, image-style first-input `match_input_image` behavior, model-specific closest-ratio fallback, and omission for anchored models that derive their ratio.
- [x] 2.5 Preserve ordered resolved reference URLs, map mutually exclusive singular/array provider fields, apply model limits, and filter unsupported Replicate parameters.
- [x] 2.6 Add dedicated video MIME classification, move MP4/MPEG video/WebM out of audio formats, and make generic analysis report unsupported video rather than transcribe it.
- [x] 2.7 Add the video screenwriter prompt fragment and resolver using the existing copywriting tool choice; defer invocation to the final video generator.
- [x] 2.8 Add `track_video_model` cost calculation and usage persistence using mapped size, mapped seconds, and failed-without-deduction behavior.
- [x] 2.9 Add or update focused offline tests for duration, size, ratio, ordered reference URLs, video classification, and video accounting; retain the reviewed existing prompt-resolver coverage policy.
- [x] 2.10 Run Ruff and the spacing checker on changed Python files, run the focused Section 2 tests, and run `git diff --check`.
- [x] 2.11 **REVIEW GATE — STOP. Present the Section 2 diff and validation evidence. Do not mark this task complete or begin Section 3 until the user explicitly approves.**

## 3. Portable video preparation

- [x] 3.1 Add architecture-neutral FFprobe JSON inspection for container, video/audio codecs, stream counts, pixel format, dimensions, duration, and byte size.
- [x] 3.2 Add FFmpeg preparation for MP4/H.264, optional AAC, `yuv420p`, fast-start metadata, and resolution reduction while preserving already compliant inputs.
- [x] 3.3 Add duration-aware target bitrate calculation, deterministic retry at lower bitrate/resolution, and post-conversion verification against destination constraints.
- [x] 3.4 Stream remote video downloads to temporary files and guarantee cleanup after success, timeout, or failure without retaining complete video bodies in memory.
- [x] 3.5 Bound preparation to two concurrent jobs per service instance and terminate FFprobe/FFmpeg subprocesses after five minutes.
- [x] 3.6 Raise structured configuration and external-service errors for missing executables, empty downloads, failed subprocesses, and outputs that cannot meet platform constraints.
- [x] 3.7 Update development and CI support so macOS ARM uses native FFmpeg, GitHub-hosted Ubuntu has FFmpeg for offline fixtures, and the existing Linux x86 Docker package remains authoritative for production.
- [x] 3.8 Add approved offline unit/integration coverage for inspection, no-op preparation, conversion, bitrate retry, concurrency, timeout, error handling, and temporary-file cleanup.
- [x] 3.9 Run Ruff and the spacing checker on changed Python files, run the focused Section 3 tests, build the Docker image, and run `git diff --check`.
- [x] 3.10 **REVIEW GATE — STOP. Present the Section 3 diff, cross-platform approach, Docker evidence, and test results. Do not mark this task complete or begin Section 4 until the user explicitly approves.**

## 4. Platform API models and transports

- [x] 4.1 Add Telegram `Video` and `Message.video` API models with file identity, dimensions, duration, optional filename/MIME/size, and caption mapping.
- [x] 4.2 Extend Telegram inbound mapping to preserve a null MIME type when Telegram omits it and reuse the existing low-level Telegram file download path.
- [x] 4.3 Verify and cover the existing WhatsApp inbound video model, caption mapper, authenticated media metadata, and download path.
- [x] 4.4 Add Telegram multipart `sendVideo` and multipart `sendDocument` API operations with captions, structured response validation, and normal HTTP timeouts.
- [x] 4.5 Add WhatsApp native video API sending through its supported media/link path with caption and structured response validation.
- [x] 4.6 Add or update focused offline API-model, mapper, and download tests for Telegram and WhatsApp; manually verify document and native-video delivery through both live platform APIs rather than mocking the HTTP integration boundary.
- [x] 4.7 Run Ruff and the spacing checker on changed Python files, run the focused Section 4 tests, and run `git diff --check`.
- [x] 4.8 **REVIEW GATE — STOP. Present the Section 4 diff and validation evidence. Do not mark this task complete or begin Section 5 until the user explicitly approves.**

## 5. Platform SDK video delivery

- [x] 5.1 Add `send_video` and `smart_send_video` contracts to the shared platform SDK.
- [x] 5.2 Mirror the existing smart photo orchestration for video, with Telegram native preference using prepared multipart video, file preference using original multipart document, and all preference using both.
- [x] 5.3 Implement WhatsApp native prepared video delivery, original document delivery through a public attachment URL, and photo/file/all preference handling.
- [x] 5.4 Persist the attachment representation actually sent by each selected delivery path and the returned outgoing platform message using existing chat context.
- [x] 5.5 Connect each platform's preparation constraints through `PlatformBotSDK.prepare_outgoing_video_attachment` beside photo/document preparation, materialize stored Telegram attachments through the attachment-storage abstraction only for multipart upload, and use public attachment URLs for WhatsApp.
- [x] 5.6 Add or update focused offline SDK tests for media preferences, preparation and persistence calls, native/document selection, captions, temporary-file cleanup, and delivery failures.
- [x] 5.7 Run Ruff and the spacing checker on changed Python files, run the focused Section 5 tests, and run `git diff --check`.
- [x] 5.8 **REVIEW GATE — STOP. Present the Section 5 diff and validation evidence. Do not mark this task complete or begin Section 6 until the user explicitly approves.**

## 6. Simple video generator and P-Video adapter

- [x] 6.1 Add a `SimpleVideoGenerator` that creates Replicate predictions through the SDK, polls terminal state with `prediction.reload()`, enforces a monotonic ten-minute deadline, and attempts `prediction.cancel()` on timeout.
- [x] 6.2 Construct one background-owned detached DI, use the normal decorated Replicate accounting path, and roll back its session after prediction creation so no request session, active transaction, or checked-out connection remains during SDK polling.
- [x] 6.3 Validate `succeeded`, `failed`, and `canceled` status before accounting, then extract the output URL in the simple generator after the decorated wait to match Replicate image generation.
- [x] 6.4 Connect the established P-Video text/reference mapping to the simple generator and verify first-image fallback, all supported ratios, 720p/1080p clamping, 4/5/10-second duration, 24 FPS, audio enabled, draft disabled, provider prompt upsampling disabled, and safety filtering disabled.
- [x] 6.5 Add focused offline simple-generator and P-Video tests for preflight, SDK polling, success, provider failure, empty-output extraction, cancellation, timeout, pricing, safety, reference truncation, and failed-without-deduction behavior.
- [x] 6.6 Run Ruff and the spacing checker on changed Python files, run the focused Section 6 tests, and run `git diff --check`.
- [x] 6.7 **REVIEW GATE — STOP. Present the Section 6 diff and validation evidence. Do not mark this task complete or begin Section 7 until the user explicitly approves.**

## 7. Veo adapters

- [x] 7.1 Connect and verify Veo 3.1 Fast text/reference input mapping, 4/6/8-second duration, 720p/1080p clamping, landscape/portrait ratio mapping, generated audio, and 15-credit-per-second pricing.
- [x] 7.2 Connect and verify Veo 3.1 standard mapping with the same normalized behavior and 40-credit-per-second pricing.
- [x] 7.3 Verify supported reference-image arrays remain in deterministic order and unsupported arrays fall back to the first-image field required by the selected Veo schema.
- [x] 7.4 Add focused offline Veo adapter tests for both models, both generation modes, reference limits, all semantic durations, ratio matching, size clamping, audio, and pricing.
- [x] 7.5 Run Ruff and the spacing checker on changed Python files, run the focused Section 7 tests, and run `git diff --check`.
- [x] 7.6 **REVIEW GATE — STOP. Present the Section 7 diff and validation evidence. Do not mark this task complete or begin Section 8 until the user explicitly approves.**

## 8. Seedance adapters

- [x] 8.1 Connect and verify Seedance 2.0 text, first-frame image, and supported reference-image array mapping without accepting video, audio, or last-frame inputs.
- [x] 8.2 Verify Seedance 2.0 ratio behavior, 4/5/10-second duration, 720p/1080p/`4k` provider mapping, generated audio, and 18/45/100-credit-per-second pricing.
- [x] 8.3 Connect and verify Seedance 2.0 Fast with the same scoped inputs, 720p clamping, generated audio, and the supplied 15-credit-per-second non-video-input rate.
- [x] 8.4 Verify that video-input parameters and the supplied video-input rates remain unreachable from the runtime contract while video editing is out of scope.
- [x] 8.5 Add focused offline Seedance tests for both models, single/multiple reference semantics, mutual exclusions, adaptive ratio, duration, resolution, audio, and cent conversion.
- [x] 8.6 Run Ruff and the spacing checker on changed Python files, run the focused Section 8 tests, and run `git diff --check`.
- [x] 8.7 **REVIEW GATE — STOP. Present the Section 8 diff and validation evidence. Do not mark this task complete or begin Section 9 until the user explicitly approves.**

## 9. Ray adapter

- [x] 9.1 Connect and verify Ray 3.2 text mapping for 5-second short/medium and 10-second long output with HDR, EXR, loop, and end-image behavior disabled.
- [x] 9.2 Verify Ray first-reference `start_image` mapping with every semantic tier clamped to 5 seconds and provider aspect ratio omitted.
- [x] 9.3 Verify 720p/1080p clamping, silent-output behavior, and averaged rates of 15/50/50 credits per second.
- [x] 9.4 Add focused offline Ray tests for text/reference modes, 10-second constraints, first-reference fallback, size/ratio behavior, disabled advanced fields, silent output, and averaged pricing.
- [x] 9.5 Run Ruff and the spacing checker on changed Python files, run the focused Section 9 tests, and run `git diff --check`.
- [x] 9.6 **REVIEW GATE — STOP. Present the Section 9 diff and validation evidence. Do not mark this task complete or begin Section 10 until the user explicitly approves.**

## 10. Final generator and chat integration

- [x] 10.1 Add the final video generator orchestration that performs screenwriter prompt enhancement internally, then invokes the selected model adapter, simple video generator, platform preparation and attachment persistence, and smart video sender.
- [x] 10.2 Add a process-local 16-slot non-blocking generation guard, launch one daemon worker per admitted job, and release the slot in every terminal path.
- [x] 10.3 Capture stable invoker/chat/configuration/reference values for the worker, construct one rolled-back detached worker DI, reuse it for persistence and delivery after a post-accounting rollback, and reconstruct fresh detached dependencies only for failure notification after that scope closes.
- [x] 10.4 Add `generate_video` to the LLM tool library with prompt, image-style comma-separated `attachment_ids` and `urls`, duration, aspect ratio, and size; resolve those ordered references, apply each adapter's limit, and report used/ignored references.
- [x] 10.5 Return immediate generating JSON for admitted work, return structured busy/validation errors before launch, stop the request progress notifier normally, and send success or failure asynchronously to the originating chat.
- [x] 10.6 Add DI factories and ChatAgent tool registration without adding an image-to-video purpose, video-edit purpose, webhook, or durable job table.
- [x] 10.7 Add approved offline orchestration tests for text-only and reference-image requests, attachment IDs and URLs, multiple-reference fallback, admission saturation, detached sessions, immediate acknowledgement, timeout, success delivery, and background failure notification.
- [x] 10.8 Run Ruff and the spacing checker on every changed Python file, run all focused video tests, run the complete offline test suite, build the Docker image, and run `git diff --check`.
- [x] 10.9 **FINAL REVIEW GATE — STOP. Present the complete diff and all validation evidence. Do not mark this task complete or perform follow-up implementation without the user's explicit approval.**
