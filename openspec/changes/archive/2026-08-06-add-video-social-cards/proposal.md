## Why

Social cards currently flatten video and animated GIF media into poster images even though the chat delivery layer can now send prepared videos. Rendering dynamic media inside the existing card design lets users share the post faithfully while an explicit image mode preserves the current static behavior.

## What Changes

- Add file-backed media preparation so remote photos, videos, GIFs, and derived outputs are streamed through scoped temporary files instead of being accumulated as complete Python byte buffers.
- Extend platform-neutral social media data with playable-media metadata while keeping each video or GIF structurally associated with its poster image.
- Add an optional social-card render mode: automatic selection by default, forced image rendering, or requested video rendering with static fallback.
- Return media placement geometry from the card template so static and dynamic renderers share one source of layout truth.
- Render main-post videos and animated GIFs inside the themed card as a sequential, rounded, padded media stack followed by the existing photo layout.
- Keep embedded-post media static, cap the complete dynamic timeline through configuration with a 120-second default, and preserve a usable static card when dynamic composition cannot complete.
- Route the rendered result through photo or video delivery according to its actual output kind.
- Divide implementation into clean architectural layers with an explicit review and verification gate after every milestone.

## Capabilities

### New Capabilities

- `file-backed-media-preparation`: Stream remote media into temporary files, process and persist media through path or stream interfaces, and guarantee cleanup without holding complete source payloads in Python memory.
- `dynamic-social-cards`: Select static or dynamic social-card output, normalize playable post media, share card geometry, compose sequential video and GIF playback, and deliver the actual output type with reliable static fallbacks.

### Modified Capabilities

None.

## Impact

- Affects attachment storage and saving interfaces, outbound photo/video preparation, social-card domain models, Twitter/X structured media fetching, card template/rendering, social-card orchestration, and the `render_social_post` LLM tool.
- Adds an optional LLM tool argument and a social-card maximum-duration configuration value; existing calls remain compatible.
- Reuses the existing Pillow, resvg, and FFmpeg runtimes; no new media runtime is expected.
- Requires offline unit and FFmpeg integration coverage for storage streaming, static rendering parity, placement metadata, composition timelines, fallback behavior, and chat delivery selection.
