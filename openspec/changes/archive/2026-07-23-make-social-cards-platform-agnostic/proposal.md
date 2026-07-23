## Why

Social card rendering is currently shaped around X/Twitter data and tooling, which makes every additional social network require invasive changes across fetching, orchestration, and rendering. The feature should render social posts from platform-neutral domain models so new networks such as Reddit can be added through adapters instead of platform-specific branches in the card renderer.

## What Changes

- Introduce a platform-neutral social post capability for rendering social cards from domain models rather than X/Twitter-specific `TweetData`.
- Refactor the existing X/Twitter social card path to become the first platform adapter that maps X API data into the shared social post domain model.
- Generalize social card rendering, embedded-post rendering, link previews, media handling, and footer branding to consume platform metadata instead of hardcoded X/Twitter assumptions.
- Add a provider-selection boundary so the orchestrator can choose the correct social post provider from the input URL.
- Preserve existing X/Twitter social card behavior while making the architecture open for future providers such as Reddit.
- Do not add Reddit support in this change; this change creates the platform-agnostic seam needed to add Reddit cleanly afterward.

## Capabilities

### New Capabilities
- `platform-agnostic-social-cards`: Rendering social cards from platform-neutral social post domain models through provider adapters.

### Modified Capabilities

## Impact

- Affected code:
  - `src/features/social_cards/social_card_orchestrator.py`
  - `src/features/social_cards/card_renderer.py`
  - `src/features/social_cards/card_template.py`
  - `src/features/social_cards/embedded_post.py`
  - `src/features/web_browsing/twitter_status_fetcher.py`
  - `src/di/di.py`
  - `src/features/chat/llm_tools/llm_tool_library.py`
  - logo configuration used by social card footers
- Affected behavior:
  - Existing X/Twitter social card rendering remains supported.
  - Unsupported social post URLs continue to fail with a validation error.
  - The renderer no longer depends on X/Twitter fetcher dataclasses.
- Dependencies:
  - No new external runtime dependency is expected for the refactor.
