## Context

The current social card implementation renders X/Twitter posts only. The LLM tool resolves `ToolType.api_twitter` before orchestration, the orchestrator parses tweet IDs and invokes `twitter_status_fetcher`, and renderer/template functions accept `TweetData` from `features.web_browsing.twitter_status_fetcher`. Footer branding is also hardcoded to X logo selection.

This works for the first platform, but it violates the desired direction for future networks: social card rendering should operate on domain concepts such as author, post text, media, link previews, embedded posts, platform branding, and source URL. Platform-specific APIs should live behind provider adapters that map external responses into those domain models.

## Goals / Non-Goals

**Goals:**
- Introduce platform-neutral social card domain models owned by `features.social_cards`.
- Make the renderer, SVG template, and embedded-post renderer depend only on those domain models and rendering asset data.
- Extract X/Twitter social card fetching into a provider adapter that maps X API data into the shared domain model.
- Make orchestration select a social post provider from the input URL before resolving platform-specific tools.
- Preserve existing X/Twitter social card output and failure behavior.
- Keep the architecture small: provider adapter, domain model, orchestrator, renderer.

**Non-Goals:**
- Add Reddit support in this change.
- Redesign the visual card layout.
- Replace the existing X API integration or caching behavior outside the social card seam.
- Add a general social network framework beyond what provider selection requires.
- Change user-facing tool settings or database schema unless required by the provider boundary.

## Decisions

### Decision: put social card domain models under `features.social_cards`

Create platform-neutral domain models in the social cards feature, such as `SocialPost`, `SocialAuthor`, `SocialMediaItem`, `SocialLinkPreview`, and `SocialPlatformBrand`.

Rationale: the renderer should depend on the feature's own domain language, not on `TweetData` from the web browsing integration. This gives the card renderer a stable input contract and keeps external API response details outside the rendering layer.

Alternative considered: keep `TweetData` and map future platforms into it. This would be faster but would bake a false platform model into every future provider.

### Decision: introduce provider adapters for URL-to-domain mapping

Define a small provider contract responsible for deciding whether it supports a URL and returning a `SocialPost`. The first implementation will be the X/Twitter provider.

Rationale: adding a platform should primarily add a provider, URL parser, mapper, and branding data. The orchestrator and renderer should remain mostly unchanged.

Alternative considered: branch in `SocialCardOrchestrator` by URL. This is acceptable for two platforms but grows into conditional orchestration and violates open/closed design.

### Decision: keep orchestration responsible for IO coordination, not platform mapping

The orchestrator should select a provider, fetch the domain post, resolve downloadable assets, choose a theme, render the card, store the attachment, and return the public URL. It should not know tweet IDs, Reddit IDs, X avatar URL size conventions, or external response shapes.

Rationale: orchestration remains the application use case, while provider adapters own platform-specific knowledge.

Alternative considered: move asset downloading into each provider. This would simplify orchestration but duplicate common avatar/media/link-preview downloading across providers.

### Decision: represent referenced content as embedded posts

Replace tweet-specific quoted/replied concepts at the rendering boundary with an optional embedded `SocialPost` plus associated assets.

Rationale: X quoted tweets, X replied-to tweets, Reddit parent comments, and future platform references are all forms of related embedded social content. The renderer only needs a nested post presentation concept.

Alternative considered: model platform-specific reference fields in the domain model. That would leak platform vocabulary into rendering and force the renderer to know which fields matter.

### Decision: platform branding is data, not template logic

Move footer logo selection from X-specific template functions to platform metadata provided through the domain model or render context.

Rationale: the template should render a platform logo chosen from metadata; it should not know about X except as data.

Alternative considered: add conditional logo functions per platform inside the template. That keeps visual code coupled to every network.

## Risks / Trade-offs

- [Risk] Existing X/Twitter cards visually change during the refactor → Mitigation: add focused tests around X domain mapping and render invocation, and compare critical rendered SVG/PNG characteristics where feasible.
- [Risk] Provider selection becomes too abstract for a single current provider → Mitigation: use a minimal provider protocol and a simple registry/list, not a framework.
- [Risk] `TwitterStatusFetcher` is also used by web browsing, so extracting models can break non-card behavior → Mitigation: preserve `TwitterStatusFetcher.as_text()` behavior and isolate social-card mapping without changing web fetch contracts unnecessarily.
- [Risk] Domain models become lowest-common-denominator and fail to support real platform differences → Mitigation: model rendering concepts, not API concepts: embedded post, media, link preview, author, brand, source URL.
- [Risk] Unsupported URLs could fail later or with less clear errors after provider selection changes → Mitigation: provider selection must fail early with a structured validation error when no provider supports the URL.
