## Context

The social-card pipeline currently fetches platform-neutral post data, downloads visual assets as Python bytes, builds one SVG containing base64 images, rasterizes it to PNG, persists the PNG, and lets the LLM tool send it as a photo. Video and animated GIF items retain only enough information to render their poster images. Separately, outbound chat delivery already downloads media to temporary paths and uses FFmpeg to inspect and prepare native video, but attachment persistence still accepts only complete byte buffers.

The change crosses shared attachment storage, integration delivery, web fetching, social-card providers, layout/rendering, orchestration, and the LLM tool. FFmpeg, Pillow, and resvg are already installed. See `proposal.md` for motivation and the capability specs for required behavior.

## Goals / Non-Goals

**Goals:**

- Keep large compressed source media file-backed from acquisition through processing and persistence.
- Preserve current outbound photo/video behavior and static-card appearance before introducing dynamic rendering.
- Enforce one-way dependencies between platform ingestion, platform-neutral domain data, layout, rendering, orchestration, persistence, and delivery.
- Give static and dynamic renderers one authoritative set of media placements.
- Make every architectural layer independently reviewable, testable, and reversible through mandatory milestone gates.
- Reuse existing media runtimes and structured error handling.

**Non-Goals:**

- Animating media inside quoted, replied-to, or embedded posts.
- Adding social platforms beyond the currently registered X provider.
- Changing existing photo tiling, card typography, theme selection, or non-media layout except where path-backed inputs require an equivalent implementation.
- Adding a background job system for social-card composition.
- Eliminating decoder pixel buffers or the bounded final PNG buffer returned by resvg; the guarantee concerns complete compressed source files and cross-layer payload copies.
- Removing the existing byte-backed attachment API or optimizing the existing persisted-card-to-delivery handoff.

## Decisions

### 1. Preserve strict layer boundaries and dependency direction

The implementation will follow this dependency flow:

```text
X fetch adapter ──▶ X social-post provider ──▶ platform-neutral post
                                                   │
                                                   ▼
remote file acquisition ──▶ scoped asset workspace/orchestrator
                                                   │
                         ┌─────────────────────────┼─────────────────────────┐
                         ▼                         ▼                         ▼
                  template + placements      static renderer         video compositor
                         └─────────────────────────┼─────────────────────────┘
                                                   ▼
                                      attachment persistence
                                                   │
LLM tool ── mode request ──▶ orchestrator result ──┴──▶ generic platform delivery
```

Platform adapters normalize their own response shapes but never make layout or delivery decisions. Layout and renderers accept platform-neutral values and paths but perform no network, storage, DI, or chat operations. The video compositor consumes a static base and placement records without knowing which provider produced them. The orchestrator owns mode resolution, resource lifetimes, renderer selection, fallback, and persistence. The LLM tool owns the user-facing mode argument and selects generic photo or video delivery from the actual result kind. `PlatformBotSDK` remains independent of social cards.

This direction is preferred over a renderer that reaches back into provider data or a social-card-specific branch inside platform delivery, both of which would cross boundaries and make isolated testing difficult.

### 2. Add generic file-backed attachment persistence before social-card work

Attachment storage will gain a path or stream upload operation, and the attachment service will gain a corresponding file-backed save entry point. Shared metadata resolution and repository persistence will be factored so byte-backed and file-backed entry points produce the same attachment records without duplicating business rules. Storage adapters will stream or copy from the supplied file rather than calling `read_bytes()`. Remote storage reads used to materialize temporary paths will also stream rather than exposing a complete `response.content` buffer.

Outbound static and video preparation will migrate to this entry point. Their current streamed temporary downloads, transforms, platform limits, metadata, and cleanup remain intact. This foundation is implemented and reviewed independently before social-card assets use it.

Adding this generic persistence boundary is preferred over letting the social-card feature access storage implementations directly. Keeping the existing byte API is preferred over a flag-day migration of every small byte-backed caller.

### 3. Own all social-card source files in one scoped workspace

One operation-scoped workspace, implemented with context managers and an exit stack or temporary directory, will own downloaded photos, video/GIF posters, playable sources, avatars, favicons, link-preview images, and derived outputs. Downloads stream in chunks to unique paths. Render assets carry paths plus platform-neutral metadata, never complete source bytes. Theme analysis and image sizing open those paths directly. The owner cleans every distinct operation-owned path after the final consumer on every exit path.

The rendered card is persisted before workspace exit. The bounded final PNG returned by the current resvg binding is written immediately to a workspace path; video composition writes directly to a workspace path. Decoder working memory is unavoidable and is not treated as retaining a source payload.

One scoped owner is preferred over independent downloader cleanup because nested assets and multiple derived files otherwise make ownership ambiguous and failure cleanup fragile.

### 4. Normalize playable variants without inferring duplicate photos

The X fetch adapter will request and parse playback variants and relevant media metadata. The X social-post provider will choose the highest-bitrate compatible MP4 variant and map it together with the preview URL as one platform-neutral video or animated GIF item. Independent photo objects remain separate. No frame hashing or image similarity is needed for X because the API supplies the relationship structurally.

Selection belongs in the provider rather than the generic renderer because variant semantics are platform-specific. The generic media model exposes only the selected playback URL, poster URL, kind, and useful dimensions/duration.

### 5. Resolve requested mode inside the orchestrator and return actual output kind

The LLM tool accepts `image`, `video`, or an omitted mode and passes it to the orchestrator. The orchestrator inspects only direct main-post media to resolve automatic mode. Image mode never downloads playable sources. Video mode and automatic dynamic mode attempt composition when direct playable media exists; missing dynamic media or any recoverable dynamic failure returns the already-rendered static card.

The result is a small platform-neutral value containing the persisted public URL and actual image/video kind. The caller branches to `smart_send_photo` or `smart_send_video`; it does not infer type from the requested mode or filename.

Returning the actual kind avoids duplicating fallback logic in the LLM tool and prevents an image fallback from being sent through the video path.

### 6. Return SVG and placements together from the template

The card template remains the authority for its incremental geometry and returns a value containing SVG content, canvas dimensions, and ordered media placements. Each placement links to one normalized media asset and records its rectangle and four corner radii. The static renderer rasterizes the SVG; the video compositor uses the same placement records to overlay motion exactly over the rendered posters.

Dynamic items are laid out first within the existing media section at the full inner content width, never the outer card width. Each receives its own full rounded mask. Photos follow and are passed through the current orientation-aware tiling rules. Static embedded-post rendering continues to use only its first available poster or photo.

Returning metadata from the existing geometry authority is preferred over reimplementing layout in the compositor. A wholesale layout-engine rewrite is unnecessary for this feature and would make visual parity harder to review.

### 7. Use a rendered static base and masked FFmpeg overlays

The template always renders poster images into a complete static base. Dynamic composition scales each playable source to its placement, applies a true rounded alpha mask, and overlays it over the matching poster. The base naturally supplies the pre-start poster and the surrounding themed design. The existing FFmpeg runtime produces a delivery-compatible MP4 with even dimensions, H.264 video, yuv420p pixels, fast-start metadata, and AAC audio when audio exists.

A true mask is preferred over decorative corner overlays because it preserves the intended shape regardless of the underlying frame. Re-rendering the SVG for every frame was rejected because it would repeatedly execute expensive text/image rendering and create a more complex frame pipeline.

### 8. Build one sequential timeline with one audio source at a time

Direct dynamic items retain source order. Each item's start is the sum of prior effective durations. Before that start, the base poster remains visible. Its moving overlay begins at the assigned timestamp, and its final frame is extended through the rest of the output. The next item begins only after the previous effective duration. Videos contribute their own audio only during their active interval; missing audio produces silence. Animated GIFs are always silent, play once, and then freeze.

The output duration is the smaller of the accumulated dynamic duration and `config.social_card_video_max_duration_s`, defaulting to 120 seconds. An item that crosses the limit is trimmed, and later items are not started.

Sequential playback is preferred over simultaneous video because mixed audio is unintelligible and selecting only the first video's audio makes later motion contextless. Freezing the last frame is preferred over dimming or branded end-state overlays for the first version because it requires no additional visual state and keeps the timeline deterministic.

### 9. Treat static fallback as a normal result

The static base is rendered before dynamic composition and remains available until persistence succeeds. Download, metadata, or composition failures are logged and converted into an image result when the base is usable. Static rendering or persistence failures still use the project's structured service errors. Empty downloads and empty process outputs are rejected.

Dynamic work will share a bounded media-processing semaphore and process timeout so concurrent requests cannot launch unbounded downloads/transcodes. The configured duration limits work per request, while existing platform preparation remains responsible for final destination byte limits.

### 10. Give the shared social-card model module a feature-specific name

Before orchestration integration, the platform-neutral social-card values will move atomically from the generic `domain.py` module to `social_card_models.py`. Every production and test import will move in the same milestone without a compatibility alias. This keeps the module's ownership clear as its render, placement, timeline, and output contracts expand, while ensuring the rename remains behavior-neutral and independently reviewable.

### 11. Make every milestone a mandatory review gate

Tasks are grouped by architectural layer. At the end of each milestone, implementation stops after targeted offline tests, lint, spacing checks, and a concise diff/test report. The gate remains incomplete until the user approves it. No task from the next milestone begins before that approval, even when an apply session could otherwise continue automatically.

This is preferred over one end-to-end branch because storage, layout parity, composition, and orchestration have different failure modes and can each be reviewed independently.

## Risks / Trade-offs

- [File-backed attachment persistence touches every storage adapter] → Implement it as the first behavior-preserving milestone, retain the byte API, and gate all later work on adapter and service tests.
- [Local image references could render differently from base64 images] → Verify resource resolution, dimensions, theme colors, and representative static card output before dynamic work begins.
- [Rounded masks or pixel-format conversion could introduce edge artifacts] → Use synthetic high-contrast offline fixtures and inspect encoded frame dimensions and corner pixels at the compositor gate.
- [Playback URLs can be unavailable or stale] → Download immediately when dynamic output is selected and treat any acquisition failure as a static fallback.
- [Sequential composition can be CPU-intensive and hold a synchronous tool call] → Bound concurrency, cap total duration at 120 seconds by default, use process timeouts, and avoid repeated SVG rendering.
- [Platform delivery can impose a lower byte limit than composition output] → Emit a standard compliant MP4 and retain the existing destination-specific preparation and document fallback.
- [Static refactoring can unintentionally change card appearance] → Complete and review static parity before introducing any moving overlays.
- [A review gate can leave later tasks intentionally incomplete] → Record completed verification and approval explicitly; resume from the next unchecked milestone after approval.

## Migration Plan

1. Introduce file-backed storage and migrate existing outbound photo/video preparation without changing feature behavior.
2. Add normalized dynamic-media metadata and mode contracts without enabling dynamic output.
3. Move static social-card assets to scoped files and return placement metadata while preserving PNG output.
4. Add and verify one dynamic media overlay with true rounded masking.
5. Add sequential multi-item timing, audio, GIF handling, ordering, and the configured duration cap.
6. Rename the shared social-card model module and verify the behavior-neutral import migration.
7. Integrate mode selection, persistence, delivery routing, and static fallbacks end to end.

Each step deploys only after its review gate. Rollback removes the most recent layer while leaving earlier, independently tested foundations in place. No database migration is required.
