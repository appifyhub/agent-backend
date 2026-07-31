## ADDED Requirements

### Requirement: Unified video generation tool selection
The system SHALL expose one `videos_gen` external tool purpose, one persisted `tool_choice_videos_gen` user selection, and one `generate_video` LLM tool for both text-to-video and reference-image-to-video generation. Video generation SHALL use Replicate as its only provider in this change.

#### Scenario: Generate from text
- **WHEN** the LLM calls `generate_video` with a prompt and no reference-image attachment IDs or URLs
- **THEN** the system resolves the user's `videos_gen` selection and starts text-to-video generation with that Replicate model

#### Scenario: Generate from reference images
- **WHEN** the LLM calls `generate_video` with a prompt and one or more reference-image attachment IDs or external URLs
- **THEN** the system resolves those inputs through the existing attachment service and starts image-conditioned video generation with the user's selected Replicate model

#### Scenario: System-agent tool resolution
- **WHEN** a system agent invokes video generation
- **THEN** the system resolves its Replicate credential through the existing access-token resolution path and uses the intelligence-preset default unless the agent has an explicit video tool override

### Requirement: Ordered reference-image inputs
The `generate_video` tool SHALL accept the same comma-separated `attachment_ids` and `urls` argument names used by image processing, preserve their resolved order, and support both input sources in the same call. A model adapter that supports multiple reference images SHALL receive the first references up to its documented maximum; an adapter that supports only one image SHALL receive only the first resolved reference.

#### Scenario: Attachment and URL references
- **WHEN** a request contains both reference-image attachment IDs and external image URLs
- **THEN** the system resolves both groups using the existing attachment and external-URL flow and presents one deterministic ordered reference list to the selected adapter

#### Scenario: Single-image model receives multiple references
- **WHEN** multiple valid references are supplied to a model that supports only one image
- **THEN** the adapter uses the first resolved image, ignores the remaining references, and includes the used and ignored counts in its generation details

#### Scenario: Multi-image model exceeds its limit
- **WHEN** the request contains more valid references than the selected model's documented array limit
- **THEN** the adapter uses the first supported subset and includes the used and ignored counts in its generation details

#### Scenario: Invalid references
- **WHEN** reference inputs were supplied but none resolves to a supported image
- **THEN** the tool returns a structured validation or external-service error without starting a background job

### Requirement: Semantic video duration
The system SHALL accept optional `short`, `medium`, and `long` duration tiers, SHALL default an omitted duration to `medium`, and SHALL map each tier to a supported model duration rather than rejecting an unavailable tier.

#### Scenario: P-Video duration mapping
- **WHEN** P-Video is selected
- **THEN** `short`, `medium`, and `long` resolve to 4, 5, and 10 seconds respectively for text-only and reference-image requests

#### Scenario: Seedance duration mapping
- **WHEN** Seedance 2.0 or Seedance 2.0 Fast is selected
- **THEN** `short`, `medium`, and `long` resolve to 4, 5, and 10 seconds respectively for text-only and reference-image requests

#### Scenario: Veo duration mapping
- **WHEN** Veo 3.1 or Veo 3.1 Fast is selected
- **THEN** `short`, `medium`, and `long` resolve to 4, 6, and 8 seconds respectively, except Veo 3.1 multi-reference generation always resolves to its required 8 seconds

#### Scenario: Ray text-only duration mapping
- **WHEN** Ray 3.2 is selected without a reference image
- **THEN** `short`, `medium`, and `long` resolve to 5, 5, and 10 seconds respectively and the 10-second request has HDR disabled

#### Scenario: Ray reference-image duration mapping
- **WHEN** Ray 3.2 is selected with at least one reference image
- **THEN** every semantic duration tier resolves to 5 seconds because Ray does not support 10-second generation with a start image

### Requirement: Normalized video resolution
The system SHALL expose `1K`, `2K`, and `4K` video size tiers, default an omitted size to `1K`, map those tiers to 720p, 1080p, and 2160p/4K respectively, and clamp a request to the selected model's highest supported resolution without rejecting it.

#### Scenario: P-Video resolution mapping
- **WHEN** P-Video receives a `1K`, `2K`, or `4K` request
- **THEN** the adapter requests 720p, 1080p, or 1080p respectively

#### Scenario: Seedance standard resolution mapping
- **WHEN** Seedance 2.0 receives a `1K`, `2K`, or `4K` request
- **THEN** the adapter requests 720p, 1080p, or provider value `4k` respectively

#### Scenario: Seedance Fast resolution mapping
- **WHEN** Seedance 2.0 Fast receives any normalized size
- **THEN** the adapter requests 720p

#### Scenario: Veo resolution mapping
- **WHEN** either Veo 3.1 model receives a `1K`, `2K`, or `4K` request
- **THEN** the adapter requests 720p, 1080p, or 1080p respectively

#### Scenario: Ray resolution mapping
- **WHEN** Ray 3.2 receives a `1K`, `2K`, or `4K` request
- **THEN** the adapter requests 720p, 1080p, or 1080p respectively

### Requirement: Normalized video aspect ratio
The system SHALL accept `9:16`, `2:3`, `3:4`, `1:1`, `4:3`, `3:2`, `16:9`, and `21:9`, preserve a supported explicit ratio, use the existing closest-numeric-ratio behavior when the selected model lacks an explicitly requested ratio, match the first input image when ratio is omitted and references exist, and otherwise default to `16:9`.

#### Scenario: Supported ratio
- **WHEN** the requested ratio is supported by the selected model
- **THEN** the adapter passes that ratio unchanged

#### Scenario: Closest supported ratio
- **WHEN** the requested ratio is not supported by the selected model
- **THEN** the adapter selects the numerically closest ratio from that model's documented ratios using the image ratio fallback behavior

#### Scenario: Singular input image source ratio
- **WHEN** generation uses one singular input image and requests `match_input_image`
- **THEN** the adapter uses its documented native input-ratio behavior without sending the unsupported literal `match_input_image`

#### Scenario: Multiple reference images
- **WHEN** generation uses multiple reference images and omits the ratio
- **THEN** the adapter uses the first image as the input-ratio reference and applies any stricter documented reference-image constraint

#### Scenario: Ratio ignored by anchored model
- **WHEN** a selected model derives its ratio directly from an anchor image
- **THEN** the adapter omits the provider ratio input instead of sending a conflicting value

### Requirement: Replicate video model catalog
The external tool catalog SHALL include P-Video, Seedance 2.0, Seedance 2.0 Fast, Veo 3.1, Veo 3.1 Fast, and Ray 3.2 as `videos_gen` tools under the Replicate provider, and SHALL describe each model's reference-image count, supported ratios, resolutions, durations, and audio behavior.

#### Scenario: Catalog and provider exposure
- **WHEN** external video tools and providers are returned through settings or profile APIs
- **THEN** all configured Replicate video models are exposed for the single `videos_gen` purpose and Replicate advertises video generation support

#### Scenario: Persisted selection
- **WHEN** a user changes their selected video model
- **THEN** the selected model ID persists and resolves through the same repository, mapper, profile merge, sponsorship, and preset paths as other tool choices

### Requirement: Screenwriter prompt enhancement
The final video generator SHALL enhance video prompts internally through a video-specific screenwriter prompt variant using the existing `copywriting` tool selection. Prompt enhancement SHALL preserve user intent while adding useful motion, pacing, camera, continuity, lighting, audio, and dialogue direction, and provider prompt rewriting SHALL be disabled wherever the selected model exposes that control. No standalone screenwriter service SHALL be introduced.

#### Scenario: Prompt enhancement succeeds
- **WHEN** a video request is admitted
- **THEN** the video generator produces the enhanced provider prompt before the Replicate prediction is created

#### Scenario: Existing copywriter selection
- **WHEN** the video generator resolves its prompt-enhancement model
- **THEN** it uses the existing copywriting tool selection and does not introduce a separate persisted screenwriter choice

#### Scenario: Reference-aware prompt enhancement
- **WHEN** reference images remain after model-limit truncation
- **THEN** the screenwriter prompt fragment receives their count and uses the fact that the video model will receive references to make the prompt clearly image-conditioned where helpful without inventing unseen visual details

### Requirement: Provider generation defaults
The adapters SHALL disable safety filtering on every model that exposes such a parameter. Initial generation SHALL omit video inputs and advanced reference controls, disable HDR, EXR export, looping, draft output, and last-frame behavior, and enable generated audio on models that support it.

#### Scenario: P-Video defaults
- **WHEN** P-Video is invoked
- **THEN** it receives `disable_safety_filter=true`, `draft=false`, 24 FPS, generated audio enabled, and provider prompt upsampling disabled

#### Scenario: Model lacks a safety switch
- **WHEN** the selected model does not expose a safety-filter parameter
- **THEN** the adapter does not invent or forward an unsupported safety field

#### Scenario: Ray initial defaults
- **WHEN** Ray 3.2 is invoked
- **THEN** HDR, EXR export, loop, and end-image inputs are disabled or omitted and the output is treated as silent

### Requirement: Cent-denominated video pricing
All video cost fields SHALL use credits, where one credit equals one US dollar cent. `CostEstimate` SHALL provide `output_video_1k_second`, `output_video_2k_second`, and `output_video_4k_second`, and cost resolution SHALL multiply the mapped output duration by the rate for the actual normalized output tier.

#### Scenario: P-Video pricing
- **WHEN** P-Video cost is estimated or recorded
- **THEN** its `1K`, `2K`, and `4K` rates are 2, 4, and 4 credits per second respectively

#### Scenario: Seedance standard pricing
- **WHEN** Seedance 2.0 cost is estimated or recorded without video input
- **THEN** its `1K`, `2K`, and `4K` rates are 18, 45, and 100 credits per second respectively

#### Scenario: Seedance Fast pricing
- **WHEN** Seedance 2.0 Fast cost is estimated or recorded without video input
- **THEN** its `1K`, `2K`, and `4K` rates are 15, 15, and 15 credits per second respectively because every normalized request maps to 720p

#### Scenario: Veo pricing
- **WHEN** Veo 3.1 Fast or Veo 3.1 is estimated or recorded with generated audio
- **THEN** every normalized size uses 15 credits per second for Fast or 40 credits per second for standard

#### Scenario: Ray averaged pricing
- **WHEN** Ray 3.2 cost is estimated or recorded
- **THEN** its `1K`, `2K`, and `4K` rates are the arithmetic average rates of 15, 50, and 50 credits per second respectively

#### Scenario: Mapped cost inputs
- **WHEN** a requested duration or size is clamped by the selected adapter
- **THEN** preflight and successful usage accounting use the mapped duration and actual normalized output tier rather than the unsupported request

### Requirement: Video usage accounting
Video predictions that reach `succeeded` SHALL record the mapped output video size and output duration in seconds together with the resolved credit cost. Failed, canceled, or timed-out predictions SHALL be recorded as failed and SHALL NOT deduct successful-output credits. The simple video generator SHALL extract the output URL after the decorated wait and accounting, matching the existing Replicate image flow.

#### Scenario: Successful prediction
- **WHEN** a prediction succeeds with a non-empty video output
- **THEN** usage records the actual normalized output size, mapped duration, and resolved video cost before or atomically with delivery persistence

#### Scenario: Failed prediction
- **WHEN** Replicate reports `failed` or `canceled` or the deadline expires
- **THEN** the system records failed usage without deducting successful-output credits

#### Scenario: Successful status with invalid output
- **WHEN** Replicate reports `succeeded` but output URL extraction fails
- **THEN** the simple video generator reports the output failure after the successful prediction has been accounted, matching Replicate image generation

### Requirement: Bounded asynchronous generation
The video tool SHALL admit at most 16 in-flight video jobs per service instance, launch admitted jobs outside the request-response path, and return a generating result immediately. The system SHALL reject an additional request with a structured busy result when all slots are occupied.

#### Scenario: Admitted background job
- **WHEN** fewer than 16 video jobs are in flight and validation succeeds
- **THEN** the tool starts a background job and returns JSON instructing the chat model to tell the partner that generation started and the video will be sent when ready

#### Scenario: Busy service
- **WHEN** 16 video jobs are already in flight on the instance
- **THEN** the tool does not create a Replicate prediction and returns a structured busy result

#### Scenario: Request completion
- **WHEN** the LLM produces its final acknowledgement after a background job starts
- **THEN** the chat request completes and its progress notifier stops without waiting for video generation

### Requirement: Prediction deadline and cancellation
The decorated video prediction SHALL poll the installed SDK prediction with `prediction.reload()` and a monotonic ten-minute generation deadline instead of invoking the SDK's unbounded raw `Prediction.wait()`. It SHALL attempt to cancel an unfinished prediction at the deadline, and its worker SHALL always release the in-flight slot.

#### Scenario: Prediction completes before deadline
- **WHEN** Replicate reaches `succeeded`, `failed`, or `canceled` before ten minutes
- **THEN** the worker stops polling and handles that terminal state

#### Scenario: Prediction exceeds deadline
- **WHEN** the prediction remains non-terminal for ten minutes
- **THEN** the worker calls the SDK cancellation operation, records a timeout failure, notifies the partner, and releases the worker slot

### Requirement: Detached worker dependencies
Background video work SHALL NOT retain the request-scoped database session. The worker SHALL construct a background-owned detached DI/session from captured invoker and chat identifiers, use the normal decorated Replicate accounting path, and call `rollback_db_session()` immediately after prediction creation. The detached session object MAY remain available to the decorator, but it SHALL hold no active transaction or checked-out database connection during prediction polling. Terminal accounting MAY lazily reacquire a connection through that session. The worker SHALL roll back again after accounting and reuse the same background DI for persistence and delivery before closing its context. Failure notification after that context exits SHALL use freshly reconstructed detached dependencies.

#### Scenario: Request session closes
- **WHEN** the responder returns after starting a video job
- **THEN** the worker continues without accessing the closed request session

#### Scenario: Completion phase
- **WHEN** polling reaches a terminal result
- **THEN** the prediction decorator records usage through the background-owned DI, the worker rolls back the accounting transaction, reuses that DI for successful persistence and delivery, and closes the context afterward

### Requirement: Asynchronous completion notification
An admitted job SHALL archive a successful provider output, prepare it for the destination platform, and send it through the smart video sender. Terminal generation or delivery failures SHALL use the existing system-announcement copywriter flow to produce a concise partner-facing message in the target chat's language because the completed request can no longer receive a tool result. The message SHALL preserve the sanitized formatted details of an existing structured service error; an unexpected exception SHALL first be represented as a structured video-generation external-service error.

#### Scenario: Successful delivery
- **WHEN** Replicate returns a valid video and platform preparation succeeds
- **THEN** the worker persists the generated attachment and sends the video according to the partner's platform and media preference

#### Scenario: Background failure
- **WHEN** generation, output extraction, preparation, persistence, or delivery fails
- **THEN** the worker logs the failure and sends the originating chat a concise localized message containing its sanitized structured error details
