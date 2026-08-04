## Context

See `proposal.md` for motivation. Image generation currently uses `SimpleImageGenerator` and `SmartImageGenerator`, while editing uses `ImageEditor`, `ChatImageEditService`, and the `process_media` editing operation. Replicate, Google AI, and xAI already have parallel generation/editing branches, and all configured image models except the retiring Flux 1.1 definition support both purposes.

Video generation provides the target request lifecycle: prompt enhancement before admission, a bounded daemon worker, detached database dependencies, immediate started details, background delivery and failure notification, and explicit transaction release while Replicate is polling. Image-provider mapping already works and is not being redesigned.

The change crosses provider adapters, accounting/session boundaries, user persistence and settings APIs, domain selections, tool catalogs, prompt fragments, LLM tools, delivery, DI, migrations, tests, and frontend documentation. Implementation proceeds outer boundary first, then domain, then service and wiring, with an explicit manual review gate after every milestone.

## Goals / Non-Goals

**Goals:**

- Preserve every meaningful generation and editing branch while consolidating provider access into one simple image adapter.
- Keep every review milestone focused and reviewable, using temporary compatibility only where a destructive cross-layer removal would otherwise leave the repository broken.
- Match smart-video asynchronous orchestration for both image modes without retaining the request database session.
- Keep public settings, persisted choices, usage purposes, and tool catalogs consistent around one image-model selection.
- Test application-owned orchestration and mapping logic offline, leaving live provider and generic media-analysis behavior for manual verification.

**Non-Goals:**

- New image models, provider SDK upgrades, or image parameter semantics. Reference inputs switch from obsolete local file transport to the providers' supported public-URL form.
- A durable job queue, cross-instance concurrency coordination, retries, cancellation, progress persistence, or job-status polling.
- WhatsApp typing or uploading indicators, because WhatsApp does not expose the platform action used here.
- Mock-based tests that merely assert third-party image API calls; those integrations remain manually tested.
- Rewriting unrelated media-analysis, attachment-resolution, smart-photo delivery, or image-resizing behavior.

## Decisions

### 1. Infer image mode from resolved reference inputs

`generate_image` gains the same attachment-ID and URL argument shape as `generate_video`. No references means text-to-image; one or more resolved references means image editing. Both modes resolve the same `images_gen` selection.

This avoids a second operation enum and keeps tool choice independent of whether a request contains references. Retaining separate LLM tools or a mode argument was rejected because either would preserve the duplication being removed.

### 2. Migrate editor behavior into the simple adapter before deleting it

`SimpleImageGenerator` initially gains optional resolved `ChatAttachment` inputs so editor behavior can be migrated safely. A later reviewed alignment moves public-URL creation, storage-stream size accounting, and model-parameter mapping to `SmartImageGenerator`, which passes one prepared `UnifiedImageParameters` value plus only the reference metadata still required by provider adapters. Provider branches are migrated from `ImageEditor` rather than reimplemented from memory. Image edit mode in the shared parameter utility is determined mechanically by the presence of input references after `ToolType.images_edit` is removed; all other mapping logic remains unchanged.

A parity checklist maps the existing editor's first-N limiting, public-URL input transport, storage-stream input sizes, MIME handling, provider parameters, Google URI parts, xAI moderation, output validation, persistence, and errors to the new code. `ImageEditor` is not deleted until this audit is complete, logic-focused tests pass, and the final side-by-side diff is reviewed.

### 3. Mirror smart-video background orchestration

`SmartImageGenerator` resolves attachment IDs and URLs to image attachments in its constructor, matching `SmartVideoGenerator`. It performs first-N selection and prompt enhancement before acquiring a process-local 16-slot non-blocking semaphore. An admitted request captures stable invoker, chat, media-mode, configured-tool, prompt, and reference values and starts a daemon worker. It returns a structured started result immediately.

The worker constructs a detached DI/session, creates the unified simple adapter from prepared parameters and reference metadata, rolls back before potentially blocking delivery, sends the result, and releases its slot in `finally`. Public URLs and input sizes are prepared before admission without downloading public URLs or creating manual temporary files. Failures use fresh detached dependencies and the existing system-announcement copywriter flow, matching video behavior. A durable queue was rejected because it exceeds the existing video contract and this change's reliability scope.

### 4. Release provider-call transactions after preflight

Provider accounting decorators own the database lifecycle created by their preflight and usage-accounting work. Simple image and video adapters remain provider adapters and do not know about accounting transactions. Each decorator receives only the narrow `rollback_db_session` callback rather than the DI container or database session.

The Replicate decorator performs preflight, rolls back, and then creates the remote prediction. Its decorated prediction rolls back again immediately before image waiting or video polling, ensuring callers cannot retain a transaction across either external boundary. Google AI and xAI image decorators perform preflight, roll back, and then invoke their synchronous provider request. In every path, usage tracking lazily begins a fresh transaction only after the provider returns. The common smart-worker rollback remains because delivery is a separate potentially blocking boundary after accounting and output persistence.

Image and video prompt enhancement follows the same boundary on the foreground DI. The smart generator's immediate media spending preflight and the copywriter or screenwriter preflight use the request session. `ChatModelUsageTrackingDecorator` and its bound runnable therefore receive the same narrow callback, roll back after their preflight, and only then invoke the external LLM. Their usage accounting begins a fresh transaction after the model returns. No explicit rollback is added to either smart generator because it would occur before the chat-model decorator's own preflight and would not protect the actual external boundary.

### 5. Apply documented image reference limits deterministically

The workflow retains the first `max_input_images` resolved references in request order and ignores later references. It reports the retained and ignored counts in its started details, and supplies the retained count to reference-aware prompt enhancement. The simple adapter defensively applies the same limit for direct callers.

This uses each selected model's existing documented input limit; it does not introduce new model limits or provider parameter mapping rules.

### 6. Use one persisted choice with deterministic migration precedence

`tool_choice_images_gen` remains nullable and authoritative. Migration first copies non-null `tool_choice_images_edit` values over it, so editing wins when both exist, then replaces Flux 1.1 with Flux 2 Pro, migrates historical usage purposes, and drops the editing column. The application removes the duplicate API/domain/preset/resolver/profile fields and ultimately removes `ToolType.images_edit` from the catalog.

The generated Alembic stub is produced only after verifying model imports. Migration code uses literal table, column, purpose, and model-ID strings rather than runtime tool definitions or configuration. Downgrade can restore a nullable empty editing column but cannot reconstruct the two original choices or distinguish pre-existing Flux 2 selections, so the data downgrade is explicitly lossy.

### 7. Set generated-media uploading status at the delivery boundary

After the provider result is ready, each detached worker requests the media-specific platform action immediately before calling its smart sender: `upload_photo` before `smart_send_photo` and `upload_video` before `smart_send_video`. The smart sender then begins its download, resizing/transcoding, persistence, and platform upload work. Telegram forwards the action and WhatsApp no-ops. `ChatProgressNotifier` is not reused because it is tied to the foreground trigger message, repeats `typing`, manages reactions, and stops when the request completes.

A one-shot action matches the requested transition from provider completion to delivery preparation. If live testing later proves preparation routinely exceeds Telegram's action lifetime, a small delivery-scoped repeater can be considered separately rather than coupling the background worker to the foreground notifier.

### 8. Keep generic media processing analysis-only

The generic LLM tool is renamed from `process_media` to `analyze_attachments`; its operation, aspect-ratio, output-size, and editing branch are removed. Editing calls move to `generate_image` with references. The established attachment processor remains unchanged.

This is a direct breaking rename rather than an alias period so the LLM sees one unambiguous route for editing. Tool-schema behavior is manually verified because mocked provider or agent-tool invocation would not add meaningful coverage.

### 9. Separate functional prompt unification from late copy polish

The unified image workflow invokes the existing copywriter for both modes and supplies the retained reference count. After functional work is reviewed, a separate milestone adds the same concise single-paragraph, few-sentence instruction to the image copywriter and video screenwriter fragments. This isolates copy changes from orchestration changes.

### 10. Use logic-focused verification and hard review gates

Existing tests are updated rather than mocking third-party image APIs. Async image coverage mirrors `test_smart_video_generator.py`: admission, thread launch, captured values, detached execution, reference handling, success delivery, upload-action ordering, failure notification, and slot release. Existing mapper, resolver, API, image-parameter, accounting, and platform-SDK tests cover owned logic.

`scratchpad.py` is append-only and may gain manual live generation/editing helpers, but automated tests do not call providers. No new test file is created without explicit user approval. Every milestone ends with a short done/tested/next report and stops for manual review.

### 11. Align the image request boundary with smart video

After the unified workflow and prompt behavior are reviewed, `SmartImageGenerator` prepares retained public URLs and storage-derived accounting sizes, maps `UnifiedImageParameters` once, and runs `SpendingService.validate_pre_flight()` before prompt enhancement, slot acquisition, or worker launch. Prompt enhancement replaces only the prepared parameter's prompt. The detached worker passes that value into `SimpleImageGenerator`, which no longer repeats URL preparation, size resolution, or model mapping inside provider branches.

This alignment is deliberately isolated in a later milestone so the provider-parity migration remains reviewable. Existing provider request fields, MIME handling, accounting metadata, response validation, and persistence remain unchanged. Verification covers application-owned preparation, preflight ordering, and worker handoff without invoking provider APIs.

### 12. Consolidate image provider methods after parity is established

After the unified adapter and prepared-parameter boundary are reviewed, `SimpleImageGenerator` uses one private method per provider. Each provider method handles text-only and reference-image inputs from the prepared constructor state while retaining its existing timeout, request shape, response validation, accounting metadata, and output persistence. This removes the remaining generate/edit method duplication without introducing a shared cross-provider abstraction.

## Risks / Trade-offs

- [Provider behavior is accidentally lost during consolidation] → Keep `ImageEditor` until the explicit provider-by-provider parity checklist and final side-by-side audit are complete.
- [A background job outlives request-scoped dependencies] → Capture identifiers and immutable values only, then reconstruct detached DI/session state inside the worker.
- [Accounting holds a database connection during prompt enhancement or provider generation] → Make chat-model and provider accounting decorators release their owning DI transaction after preflight and before external I/O; Replicate also releases immediately before decorated waiting or polling. Keep simple and smart generators free of accounting transaction ownership and retain the separate smart-worker rollback before delivery.
- [Removing the edit choice changes a user's selected model] → Give the former editing choice deterministic precedence and document it in API changes and `CHANGES.md`.
- [Partial milestone changes temporarily span old and new contracts] → Use the smallest explicit compatibility bridge necessary and remove it in the middle-layer milestone; never leave a review gate with known failing focused tests.
- [One-shot Telegram upload status expires during long media preparation] → Place it immediately before smart delivery and leave repetition to a separately justified follow-up if manual testing demonstrates a real gap.
- [Async failures can no longer return through the LLM tool] → Use the established localized system-announcement failure path from video generation.
- [Migration downgrade cannot restore overwritten choices] → Mark downgrade as lossy and restore only schema compatibility.

## Migration Plan

1. Add unified optional-reference behavior to the simple image adapter and complete the editor parity audit while the old path remains available.
2. Remove the separate public/persisted image-edit choice from outer contracts, retaining only a minimal internal compatibility bridge needed by the not-yet-switched service layer.
3. Verify `src/db/alembic/env.py` model imports, ask the user to run `./tools/db_generate_migration -y`, and fill the generated stub with literal data updates and the generated column removal.
4. Remove duplicated inner domain choice/default/merge behavior while keeping focused tests passing.
5. Switch smart orchestration, LLM image tooling, delivery, and DI to the unified async flow; then remove the legacy editor, edit service, tool purpose, catalog typing, and compatibility bridge.
6. Rename the analysis tool and remove its editing contract.
7. Apply the concise image/video prompt-fragment polish.
8. Align image preflight and unified-parameter handoff with smart video without changing provider behavior.
9. Update API documentation and error codes and create `CHANGES.md` for the frontend agent.
10. Consolidate the image adapter into one private method per provider, move provider-call transaction release from simple adapters into the Replicate, Google AI, and xAI accounting decorators, and release the foreground transaction in the chat-model decorator before image/video prompt enhancement.
11. Align image and video upload actions at the result-ready delivery boundary.
12. Refresh the frontend handoff and run all focused and complete offline checks.

Database deployment applies the migration before starting the new application version. Rolling application code back requires restoring the prior API/tool contracts; the downgrade can recreate the nullable legacy column but cannot recover overwritten selection data.
