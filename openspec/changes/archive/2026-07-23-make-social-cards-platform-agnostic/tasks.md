## 1. Domain Model

- [x] 1.1 Add platform-neutral social card domain models under `features.social_cards`
- [x] 1.2 Represent author, content, media, link previews, embedded posts, source URL, and platform branding without X/Twitter-specific names
- [x] 1.3 Add render asset data structures for downloaded avatar, media, link preview, and embedded-post assets
- [x] 1.4 Stop for user review of domain model milestone

## 2. Provider Boundary

- [x] 2.1 Define a minimal social post provider contract for URL support checks and domain post fetching
- [x] 2.2 Implement the X/Twitter provider by reusing existing X API fetching and mapping responses into the neutral domain model
- [x] 2.3 Move X-specific URL parsing, tweet ID handling, referenced tweet handling, and avatar URL sizing behind the X provider boundary
- [x] 2.4 Register providers through DI or an equivalent explicit provider list used by the orchestrator
- [x] 2.5 Stop for user review of provider boundary milestone

## 3. Orchestration

- [x] 3.1 Update `SocialCardOrchestrator` to select a provider from the input URL before resolving platform-specific tools
- [x] 3.2 Keep shared asset downloading, link preview asset resolution, theme selection, rendering, attachment storage, and public URL creation in the orchestrator
- [x] 3.3 Return a structured validation error when no registered provider supports the submitted URL
- [x] 3.4 Preserve existing X/Twitter success and referenced-post failure tolerance behavior
- [x] 3.5 Stop for user review of orchestration milestone

## 4. Rendering

- [x] 4.1 Update `card_renderer` to accept the neutral social post model and render assets instead of `TweetData` and untyped dictionaries
- [x] 4.2 Update `card_template` to render neutral post fields and platform branding metadata
- [x] 4.3 Update `embedded_post` to render neutral embedded posts instead of tweet-specific data
- [x] 4.4 Replace hardcoded X footer logo selection with metadata-driven platform logo selection
- [x] 4.5 Remove social card renderer imports from `features.web_browsing.twitter_status_fetcher`
- [x] 4.6 Stop for user review of rendering milestone

## 5. Verification

- [x] 5.1 Add focused tests for platform-neutral social card domain models
- [x] 5.2 Leave platform-specific provider tests out of scope for this change
- [x] 5.3 Add focused tests proving renderer/template code consumes neutral social post data
- [x] 5.4 Run lint and spacing checks on changed Python files
- [x] 5.5 Run the targeted offline tests covering social card domain and rendering boundaries
- [x] 5.6 Stop for user review of verification milestone
