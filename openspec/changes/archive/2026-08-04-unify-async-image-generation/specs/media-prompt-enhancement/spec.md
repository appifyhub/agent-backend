## Purpose

Keeps generated-media prompts useful and reference-aware while preventing copywriter and screenwriter enhancement from producing unnecessarily long provider prompts.

## ADDED Requirements

### Requirement: Image prompt enhancement in both modes
The image workflow SHALL enhance prompts for text-only generation and reference-image editing through the existing copywriting tool selection. Reference-image enhancement SHALL receive the number of retained references after applying the selected model's input limit and SHALL preserve the partner's requested transformation without inventing unseen visual details.

#### Scenario: Text-only image prompt
- **WHEN** an image request contains no references
- **THEN** the copywriter enhances the text-only generation prompt before the background job starts

#### Scenario: Reference-image prompt
- **WHEN** an image request retains one or more resolved references
- **THEN** the copywriter is told their actual count and enhances the request as image-conditioned work

### Requirement: Concise generated-media prompts
Image copywriter and video screenwriter prompt fragments SHALL direct their model to return no more than a few sentences and SHALL prohibit multi-paragraph output.

#### Scenario: Image prompt is enhanced
- **WHEN** the image copywriter returns an enhanced prompt
- **THEN** its instruction requests a concise single-paragraph result of at most a few sentences

#### Scenario: Video prompt is enhanced
- **WHEN** the video screenwriter returns an enhanced prompt
- **THEN** its instruction requests a concise single-paragraph result of at most a few sentences

### Requirement: Prompt-enhancement transaction release
Image copywriter and video screenwriter accounting SHALL release the foreground DI transaction after preflight and before invoking the external language model. Direct chat-model invocation and tool-bound runnable invocation SHALL preserve the same boundary, and usage accounting SHALL begin a fresh transaction after the model returns.

#### Scenario: Image or video prompt enhancement starts
- **WHEN** the chat-model accounting preflight succeeds for image copywriting or video screenwriting
- **THEN** the foreground transaction is rolled back before the external model is invoked
- **AND** usage accounting starts a fresh transaction after the model returns

#### Scenario: Tool-bound model invocation starts
- **WHEN** a tool-bound runnable completes accounting preflight
- **THEN** it applies the same rollback-before-model boundary as direct invocation
