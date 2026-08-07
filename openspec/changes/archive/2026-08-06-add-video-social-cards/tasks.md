## 1. Milestone 1: File-Backed Media Foundation

- [x] 1.1 Extend the attachment storage protocol and every local, S3, and Uploadcare adapter with file-backed persistence and streamed remote reads, preserving MIME metadata and public/private URI behavior.
- [x] 1.2 Add a file-backed attachment-service save path and share metadata resolution, replacement cleanup, and repository persistence with the existing byte-backed path without duplicating business rules.
- [x] 1.3 Migrate outgoing static-photo and video preparation to persist prepared paths without `read_bytes()`, preserving size limits, transforms, captions, thumbnails, media modes, and fallbacks.
- [x] 1.4 Extend the existing attachment storage, attachment service, platform SDK, image preparation, and video preparation tests with offline success, failure, streamed-transfer, metadata-parity, and temporary-cleanup coverage.
- [x] 1.5 Run targeted offline tests plus `pipenv run ruff check --fix` and `pipenv run python tools/check_spacing.py --fix` on every Python file changed in this milestone; record the commands and results.
- [x] 1.6 **REVIEW GATE:** Present the Milestone 1 diff, boundary decisions, test evidence, and remaining risks; stop and mark this gate complete only after user approval, and do not begin Milestone 2 beforehand.

## 2. Milestone 2: Platform-Neutral Dynamic Media Contracts

- [x] 2.1 Extend structured X media fetching to request and parse playback variants, duration, dimensions, and preview metadata without changing text-oriented fetch behavior or cached response handling.
- [x] 2.2 Extend the X social-post provider to select the highest-bitrate compatible MP4 variant and map each video or animated GIF together with its poster as one platform-neutral media item while preserving independent photos.
- [x] 2.3 Add platform-neutral render-mode, output-kind, rendered-result, and dynamic-media metadata types without introducing provider, renderer, persistence, or chat dependencies into the domain layer.
- [x] 2.4 Extend existing Twitter fetcher, provider, and social-card domain tests for variant selection, GIF mapping, independent photos, missing variants, and poster association.
- [x] 2.5 Run targeted offline tests and the required lint and spacing commands on Milestone 2 files; record the commands and results.
- [x] 2.6 **REVIEW GATE:** Present the Milestone 2 diff, normalized contracts, test evidence, and remaining risks; stop and mark this gate complete only after user approval, and do not begin Milestone 3 beforehand.

## 3. Milestone 3: Path-Based Static Cards and Shared Geometry

- [x] 3.1 Introduce an operation-scoped social-card asset workspace that streams remote visual assets to unique temporary paths, tracks ownership, and cleans every downloaded or derived path on success and failure.
- [x] 3.2 Move main-post and embedded-post photos, dynamic posters, avatars, favicons, and link-preview images to path-backed render assets while keeping remote acquisition outside domain, layout, and renderer layers.
- [x] 3.3 Update theme analysis, image sizing, link previews, embedded posts, and SVG image references to consume local paths while preserving current static-card content and styling.
- [x] 3.4 Return SVG content, canvas dimensions, and ordered media-placement records from the template; place direct dynamic posters in padded full-width rows before photos and keep current photo tiling below them.
- [x] 3.5 Make the static renderer produce a workspace output path and persist it through file-backed attachment saving while preserving the current image-card API and delivery behavior.
- [x] 3.6 Extend existing social-card tests with offline path-backed acquisition, recursive asset cleanup, static rendering parity, mixed-media ordering, inner-padding, rounded-placement metadata, and failure cleanup coverage.
- [x] 3.7 Run targeted offline tests and the required lint and spacing commands on Milestone 3 files; render representative cards for review and record all results.
- [x] 3.8 **REVIEW GATE:** Present the Milestone 3 diff, representative static artifacts, placement data, test evidence, and remaining risks; stop and mark this gate complete only after user approval, and do not begin Milestone 4 beforehand.

## 4. Milestone 4: Single Dynamic Media Composition

- [x] 4.1 Add the configurable social-card video duration limit with a 120-second default and structured errors for invalid, empty, timed-out, or failed composition outputs.
- [x] 4.2 Add a provider-agnostic video-card compositor that reads one playable source path, the rendered static base, and its placement record, then writes a compliant MP4 to a temporary output path under bounded media-processing concurrency.
- [x] 4.3 Scale the moving image to the exact padded placement and apply a true four-corner alpha mask before overlaying it over the matching poster, preserving even output dimensions and the complete surrounding card design.
- [x] 4.4 Preserve source audio when present, generate a silent segment when absent, trim at the configured duration, and freeze the final frame through the output end.
- [x] 4.5 Extend existing offline social-card/video tests with synthetic FFmpeg fixtures covering one landscape and portrait video, audio and silent inputs, exact placement, visible rounded corners, duration trimming, compliant output metadata, process failure, and cleanup.
- [x] 4.6 Run targeted offline tests and the required lint and spacing commands on Milestone 4 files; render and inspect representative video-card frames and record all results.
- [x] 4.7 **REVIEW GATE:** Present the Milestone 4 diff, representative video artifact and frames, test evidence, and remaining risks; stop and mark this gate complete only after user approval, and do not begin Milestone 5 beforehand.

## 5. Milestone 5: Sequential Multi-Media Timeline

- [x] 5.1 Add a pure timeline planner that assigns source-ordered start times and effective durations from inspected direct-media metadata under one accumulated duration cap.
- [x] 5.2 Compose multiple dynamic placements so each shows its poster before activation, plays only in its interval, freezes its final frame afterward, and leaves later items unstarted once the output cap is reached.
- [x] 5.3 Build one sequential audio track in which only the active video contributes audio, silent videos contribute silence, and animated GIF items always remain silent.
- [x] 5.4 Treat animated GIF playback variants as one-play dynamic segments and preserve videos/GIFs as stacked padded rows before the unchanged independent-photo layout.
- [x] 5.5 Extend existing offline social-card/video tests for two videos, mixed audio availability, video plus GIF, GIF-only output, source ordering, freeze behavior, accumulated truncation at 120 seconds, and omission of later items.
- [x] 5.6 Run targeted offline tests and the required lint and spacing commands on Milestone 5 files; render and inspect a representative multi-item timeline and record all results.
- [x] 5.7 **REVIEW GATE:** Present the Milestone 5 diff, representative timeline artifact, test evidence, and remaining risks; stop and mark this gate complete only after user approval, and do not begin Milestone 6 beforehand.

## 6. Milestone 6: Social-Card Model Module Naming

- [x] 6.1 Rename `domain.py` to `social_card_models.py` and atomically update every production and test import without compatibility aliases or behavior changes.
- [x] 6.2 Run the social-card tests plus the required lint and spacing commands on every renamed or import-updated Python file; confirm no stale `features.social_cards.domain` imports remain.
- [x] 6.3 **REVIEW GATE:** Present the Milestone 6 rename diff and verification evidence; stop and mark this gate complete only after user approval, and do not begin Milestone 7 beforehand.

## 7. Milestone 7: Orchestration, Fallback, and Delivery

- [x] 7.1 Resolve omitted, image, and video modes in the social-card orchestrator using only direct main-post dynamic media; keep embedded-post media static and avoid downloading playable sources in image mode.
- [x] 7.2 Render and retain the static base before dynamic work, fall back to that image after recoverable playback download, inspection, or composition failures, and persist the successful actual output through file-backed saving.
- [x] 7.3 Return the persisted public URL with its actual image/video kind and update the LLM tool to accept the optional mode and route results through `smart_send_photo` or `smart_send_video` accordingly.
- [x] 7.4 Preserve existing media-mode behavior and document fallbacks for both actual output kinds, including automatic or requested video attempts that return image fallbacks.
- [x] 7.5 Extend existing orchestrator, LLM tool, and integration tests for every mode, direct versus embedded dynamic media, unavailable playback, composition failure, result-kind routing, GIF behavior, and cleanup across success and fallback paths.
- [x] 7.6 Update applicable tool and configuration documentation for mode semantics, main-post-only animation, static fallback, sequential playback, and the 120-second default.
- [x] 7.7 Run the complete offline test suite with `pipenv run pytest -v`, then run the required lint and spacing commands on every Python file changed by the change; record final results and confirm no new media runtime dependency was introduced.
- [x] 7.8 **FINAL REVIEW GATE:** Present the complete layered diff, documentation, representative image/video artifacts, full test evidence, and unresolved risks; stop and mark the change implementation complete only after user approval.
