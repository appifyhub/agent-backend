## Why

Image generation and editing currently use separate tool choices, classes, and chat flows even though nearly every configured image model supports both operations. Unifying them behind one asynchronous image workflow will remove duplicated behavior, align image generation with video generation, and keep long-running provider work outside the chat request.

## What Changes

- Merge text-to-image generation and reference-image editing behind one `generate_image` tool and one selected image model.
- Make image generation and editing asynchronous, with bounded detached workers, immediate started responses, background delivery, and background failure notification matching video generation.
- Preserve the current Replicate, Google AI, and xAI editing behavior when it is migrated into the simple image generator, while replacing obsolete public-URL downloads and manual temporary files with direct provider URLs and storage-stream accounting. Complete an explicit line-by-line parity audit before the old editor is removed.
- Enhance prompts for both text-only and reference-image requests, using the selected model's documented first-N reference limit without changing established image parameter mapping.
- Consolidate each image provider's text-only and reference-image branches into one private adapter method without changing provider behavior.
- Move provider-call transaction release into the Replicate, Google AI, and xAI accounting decorators so preflight completes before every external generation call and no simple image or video adapter owns accounting session lifecycle.
- Release the foreground image/video preflight transaction through the chat-model accounting decorator before copywriter or screenwriter prompt enhancement invokes its external LLM.
- Set Telegram's `upload_photo` or `upload_video` chat action after a generated result is ready and immediately before platform preparation and delivery; retain WhatsApp's existing no-op behavior.
- **BREAKING** Remove the separate `images_edit` external-tool purpose and persisted/API `tool_choice_images_edit` setting. The migration gives the former editing choice precedence when both image choices are populated.
- Remove Flux 1.1 Pro and migrate its remaining selections to Flux 2 Pro.
- **BREAKING** Rename the analysis-only `process_media` LLM tool to `analyze_attachments`, remove its operation argument, and move image editing to `generate_image` references.
- Constrain the image copywriter and video screenwriter prompt fragments to a few sentences rather than multiple paragraphs.
- Align the image request boundary with video by mapping one unified parameter object before worker admission, running image spending preflight synchronously, and passing the prepared parameters into the simple adapter.
- Produce a final `CHANGES.md` describing frontend-facing API, selector, tool-schema, documentation, and error-code changes.

## Capabilities

### New Capabilities

- `unified-image-generation`: One asynchronous workflow for text-only image generation and reference-image editing, including prompt enhancement, detached execution, delivery status, and failure notification.
- `image-tool-selection`: One persisted and API-visible image-model selection, including legacy choice precedence, Flux migration, usage-purpose migration, and catalog cleanup.
- `media-analysis`: An analysis-only `analyze_attachments` LLM tool with image editing removed from the generic media-processing contract.
- `media-prompt-enhancement`: Concise, reference-aware image copywriter and video screenwriter prompt enhancement.
- `generated-media-delivery`: Image and video upload actions at the shared result-ready delivery boundary.

### Modified Capabilities

None. There are no current baseline OpenSpec capabilities for image generation, image tool selection, or generic media analysis.

## Impact

- Image provider adapters, image parameter mapping, prompt resolvers, accounting decorators, detached-session handling, chat delivery, progress actions, failure announcements, DI factories, and LLM tool registration.
- External tool definitions, tool purposes, intelligence presets, user/domain/DB models, repositories, API payloads and responses, profile merging, sponsorship/default selection, usage-purpose persistence, and Alembic migration data.
- Public settings and LLM tool contracts are breaking for frontend and agent-tool consumers that still use the separate image-edit selector or `process_media` editing operation.
- Existing logic-focused tests will be updated to mirror smart-video orchestration coverage. Live provider and media-analysis API behavior remains manually verified rather than mocked.
