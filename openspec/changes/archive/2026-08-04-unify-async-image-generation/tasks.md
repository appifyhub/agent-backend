## 1. Outer image provider adapter and parity

- [x] 1.1 Inspect the nearest existing tests for every affected layer; update existing test files where useful and obtain explicit user approval before creating any new test file. Do not add mocked provider-call tests.
- [x] 1.2 Extend `SimpleImageGenerator` with optional resolved reference-image attachments; in its constructor, retain the first supported inputs, derive public provider URLs and accounting sizes, and preserve text-only behavior for existing callers.
- [x] 1.3 Migrate the Replicate editing path from `ImageEditor`, including direct public-URL input transport, storage-stream input-size accounting, unified parameters, provider filtering, preflight metadata, result extraction, output persistence, and structured empty-response behavior.
- [x] 1.4 Establish Replicate transaction release before decorated waiting, initially matching the existing video flow; Section 9 moves final ownership into the accounting decorator and also releases before prediction creation.
- [x] 1.5 Migrate the Google AI editing path from `ImageEditor`, including public URL URI parts, MIME handling, input-size accounting, image configuration, response validation, inline output extraction, and output persistence.
- [x] 1.6 Migrate the xAI editing path from `ImageEditor`, including direct public-URL reference inputs, moderation handling, response validation, output decoding, and output persistence.
- [x] 1.7 Change shared image parameter mode detection mechanically from the legacy tool purpose to the presence of input files without changing existing ratio, size, resolution, or provider mappings.
- [x] 1.8 Perform and present a side-by-side parity audit covering every editor field, provider branch, parameter, error path, public-URL transport, input metric, response check, and persistence step. The only intentional validation difference is retaining the first `max_input_images` inputs. Keep `ImageEditor` and its current callers in place.
- [x] 1.9 Append, without removing or rewriting existing helpers, any `scratchpad.py` functions needed for the user's manual live generation/editing checks; automated verification SHALL NOT invoke provider APIs.
- [x] 1.10 Run Ruff and the spacing checker on changed Python files, run the existing focused image-parameter and accounting tests that cover application logic, and run `git diff --check`.
- [x] 1.11 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 2 until the user explicitly approves.**

## 2. Outer settings, catalog, persistence, and migration

- [x] 2.1 Remove `tool_choice_images_edit` from user settings payloads, responses, API mapping, and public API documentation so only nullable `tool_choice_images_gen` remains visible.
- [x] 2.2 Remove the duplicate image-edit column from the user DB model and update persistence mapping while retaining only the smallest temporary internal compatibility needed by the not-yet-switched domain and service layers.
- [x] 2.3 Remove Flux 1.1 Pro from the external tool library and verify Flux 2 Pro remains selectable. Defer removal of any legacy internal edit-purpose typing still required by the current middle layer until Section 4.
- [x] 2.4 Audit `src/db/alembic/env.py` model imports and the current Alembic head, then ask the user to run `./tools/db_generate_migration -y`; do not create or apply the migration independently.
- [x] 2.5 Fill the generated migration stub with literal data updates that copy non-null editing choices over generation choices, replace Flux 1.1 Pro with Flux 2 Pro, rewrite historical `images_edit` usage purposes to `images_gen`, and then drop the legacy column. Document the downgrade as lossy and avoid runtime tool/config imports.
- [x] 2.6 Audit every adjacent persistence, settings, mapper, profile, sponsorship, system-agent, preset, and historical-migration path for the removed property, leaving inner-domain cleanup to Section 3.
- [x] 2.7 Review existing API, mapper, repository, catalog, and usage tests; update only tests covering changed application-owned behavior, and validate deterministic migration SQL offline without applying it to the user's database.
- [x] 2.8 Run Ruff and the spacing checker on changed Python files, run the focused Section 2 tests, inspect migration upgrade/downgrade and the single Alembic head, and run `git diff --check`.
- [x] 2.9 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 3 until the user explicitly approves.**

## 3. Inner image-selection domain

- [x] 3.1 Remove the duplicate image-edit choice from the user domain and its construction, copying, comparison, and update paths while keeping `tool_choice_images_gen` nullable.
- [x] 3.2 Collapse intelligence-preset and default-tool selection onto one image model for generation and editing, preserving preset defaults when no explicit override exists.
- [x] 3.3 Update tool-choice resolution, profile merge, sponsorship, and system-agent paths to resolve the unified generation choice; retain only a private compatibility route for the old edit service until Section 4.
- [x] 3.4 Update existing user mapper/repository, preset, resolver, profile-merge, sponsorship, and system-agent tests for the unified domain selection.
- [x] 3.5 Run Ruff and the spacing checker on changed Python files, run the focused Section 3 tests, and run `git diff --check`.
- [x] 3.6 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 4 until the user explicitly approves.**

## 4. Middle unified asynchronous image workflow

- [x] 4.1 Extend `SmartImageGenerator` to validate the prompt and resolve optional attachment IDs and URLs through the existing image-attachment service in its constructor. Retain the first selected-model-supported references in request order and report the retained and ignored counts like smart video.
- [x] 4.2 Run the existing image copywriter for both text-only and reference-image modes and supply the retained reference count before background admission.
- [x] 4.3 Add a process-local 16-slot non-blocking image guard, start admitted work in a daemon thread, capture only stable values, and return immediate started details including retained and ignored reference counts.
- [x] 4.4 Implement a detached image worker that reconstructs DI/session state, invokes the unified simple generator, rolls back before delivery, releases its slot in every terminal path, and uses fresh detached dependencies for localized background failure announcements.
- [x] 4.5 Request `upload_photo` from `PlatformBotSDK` after the provider result is ready and immediately before `smart_send_photo`; preserve Telegram forwarding and WhatsApp no-op behavior without reusing `ChatProgressNotifier`.
- [x] 4.6 Extend `generate_image` with comma-separated `attachment_ids` and `urls`, resolve the single `images_gen` selection, and return video-style started details rather than synchronous delivery confirmation.
- [x] 4.7 Move attachment resolution, reference MIME/URL preparation, and delivery responsibilities still needed from `ChatImageEditService` into the unified flow.
- [x] 4.8 Repeat the complete side-by-side editor parity audit against the finished unified path. Only after it passes, remove `ImageEditor`, `ChatImageEditService`, their DI factories, and obsolete tests/wiring.
- [x] 4.9 Remove the remaining internal `images_edit` tool type, resolver/default compatibility, dual catalog typing, edit-specific usage creation, and orphaned imports or error handling created obsolete by this change.
- [x] 4.10 Update existing smart-image and former chat-edit tests with logic-only coverage patterned after `test_smart_video_generator.py`: reference resolution and first-N limiting, admission, immediate response, thread capture, detached execution, session release, delivery, upload-action ordering, failure notification, and slot release. Do not mock provider API calls.
- [x] 4.11 Run Ruff and the spacing checker on changed Python files, run the focused smart-image, platform-SDK, resolver, catalog, usage, and DI tests, and run `git diff --check`.
- [x] 4.12 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 5 until the user explicitly approves.**

## 5. Analysis-only media tool

- [x] 5.1 Rename `process_media` to `analyze_attachments`, remove its operation, aspect-ratio, and output-size arguments, and retain its existing attachment-analysis behavior.
- [x] 5.2 Remove the image-edit operation constants, routing, edit-specific errors that become unused, and old tool registration; update tool documentation so reference-image creation points to `generate_image`.
- [x] 5.3 Update chat-agent tool registration and any prompt/tool-name references to expose `analyze_attachments` and unified `generate_image` without a compatibility alias.
- [x] 5.4 Manually verify the tool schema and representative analysis routes; do not add mocked API or agent-tool tests solely for this rename. Run any existing lightweight registration or attachment-processing tests that already cover the changed logic.
- [x] 5.5 Run Ruff and the spacing checker on changed Python files and run `git diff --check`.
- [x] 5.6 **REVIEW GATE — STOP. Report briefly what was done, the manual testing strategy/results, and what comes next. Do not mark this task complete or begin Section 6 until the user explicitly approves.**

## 6. Generated-media prompt polish

- [x] 6.1 Update the image copywriter prompt fragment to require a concise single-paragraph result of no more than a few sentences while preserving reference-aware instructions.
- [x] 6.2 Update the video screenwriter prompt fragment with the same few-sentence, no-multiple-paragraph constraint without changing video parameter or reference-limit logic.
- [x] 6.3 Run existing prompt-resolver or smart-generator tests that cover application-owned argument forwarding, manually inspect both resolved prompt fragments, run Ruff and spacing checks on changed files, and run `git diff --check`.
- [x] 6.4 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 7 until the user explicitly approves.**

## 7. Image request boundary alignment

- [x] 7.1 Move retained-reference public-URL preparation and storage-stream size accounting into `SmartImageGenerator`, then map one `UnifiedImageParameters` value before prompt enhancement and worker admission.
- [x] 7.2 Run `SpendingService.validate_pre_flight()` synchronously with the selected image tool, mapped output size, and retained input sizes before invoking the copywriter, acquiring a slot, or starting a worker.
- [x] 7.3 Replace only the prepared parameter prompt after enhancement and pass the unified parameters plus required reference MIME/accounting metadata through the detached worker and DI into `SimpleImageGenerator`. Remove repeated URL preparation, size resolution, and model mapping from the simple adapter without changing provider requests, accounting metadata, response handling, or persistence.
- [x] 7.4 Update existing smart-image tests for owned preflight ordering, arguments, and unified worker handoff. Do not create provider-call tests or a new test file.
- [x] 7.5 Repeat the provider-parity audit for every generated parameter and retained-reference metadata field, run focused smart-image, image-parameter, accounting, and DI tests, then run Ruff, spacing, and `git diff --check`.
- [x] 7.6 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 8 until the user explicitly approves.**

## 8. Frontend handoff and final validation

- [x] 8.1 Audit and update API/OpenAPI documentation for the removed image-edit selector and purpose, unified async `generate_image` contract, and `analyze_attachments` rename.
- [x] 8.2 Audit all affected error codes and remove only codes made unused by this change; preserve existing image validation codes and document every error-code contract change.
- [x] 8.3 Create `CHANGES.md` for the frontend agent covering selector/property removals, migration precedence, Flux replacement, tool-purpose and LLM-tool changes, async response details, reference arguments, API documentation, and error codes.
- [x] 8.4 Confirm `scratchpad.py` changes are additive only and present the manual live checklist for generation and editing across the configured providers plus representative media analysis.
- [x] 8.5 Run Ruff and the spacing checker on every changed Python file, run `git diff --check`, validate the OpenSpec change strictly, and run the complete offline test suite before handing any remaining work to the user.
- [x] 8.6 **FINAL REVIEW GATE — STOP. Report briefly the completed scope, complete validation evidence, manual checks remaining for the user, and the frontend handoff file. Do not mark this task complete or perform follow-up implementation without explicit approval.**

## 9. Simple image provider-method consolidation

- [x] 9.1 Audit each Replicate, Google AI, and xAI generation/editing method pair and freeze every intentional difference before editing.
- [x] 9.2 Replace each provider pair with one private provider method that handles optional references while preserving request fields, timeouts, transaction release, accounting metadata, response validation, moderation, and persistence.
- [x] 9.3 Repeat the provider-parity audit, run existing logic-focused image tests without provider API mocks, then run Ruff, spacing, and `git diff --check`.
- [x] 9.4 Move provider-call transaction ownership out of the simple image and video adapters. Inject the narrow rollback callback into Replicate, Google AI, and xAI accounting decorators; release after preflight and before every external generation call, release again before Replicate waiting or polling, preserve the separate smart-worker delivery rollback, and verify ordering with existing focused decorator and smart-generator tests.
- [x] 9.5 Inject the same DI-bound rollback callback into the chat-model accounting decorator and its bound runnable so image copywriting and video screenwriting release foreground preflight transactions before external LLM calls; verify the complete preflight, rollback, model, and accounting order in the existing decorator tests.
- [x] 9.6 **REVIEW GATE — STOP. Report briefly what was consolidated, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 10 until the user explicitly approves.**

## 10. Generated-media upload status boundary

- [x] 10.1 Extend the platform and Telegram chat-action contracts with `upload_video` while retaining WhatsApp's no-op behavior.
- [x] 10.2 After each provider result is ready, request `upload_photo` immediately before `smart_send_photo` and `upload_video` immediately before `smart_send_video`, so the action precedes SDK download, resizing/transcoding, persistence, and upload work.
- [x] 10.3 Update only the existing smart-image and smart-video orchestration tests for action ordering; do not add provider-call or standalone forwarding tests.
- [x] 10.4 Run focused smart-image and smart-video tests, Ruff, spacing, and `git diff --check`.
- [x] 10.5 **REVIEW GATE — STOP. Report briefly what was done, the testing strategy/results, and what comes next. Do not mark this task complete or begin Section 11 until the user explicitly approves.**

## 11. Refreshed handoff and final validation

- [x] 11.1 Refresh `CHANGES.md` and the manual checklist for consolidated provider methods and image/video upload actions.
- [x] 11.2 Run Ruff and spacing on every changed Python file, `git diff --check`, strict OpenSpec validation, and the complete offline test suite.
- [x] 11.3 **FINAL REVIEW GATE — STOP. Report briefly the completed scope, complete validation evidence, manual checks remaining for the user, and the frontend handoff file. Do not mark this task complete or perform follow-up implementation without explicit approval.**
