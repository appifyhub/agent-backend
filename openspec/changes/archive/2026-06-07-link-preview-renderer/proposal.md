## Why

Tweets containing external URLs currently display raw `t.co` shortened links in the social card text, which are ugly and meaningless to the viewer. Additionally, t.co links referencing the tweet's own media (photos) are redundant since we already render those as attached images. We need to strip self-referencing URLs and render external links as rich preview cards — similar to how Twitter/iMessage render link previews.

## What Changes

- Strip t.co URLs from tweet text when they reference the tweet's own media
- Request `entities` field from Twitter API to get URL expansion metadata
- Build a new link preview renderer that generates SVG snippets for external URLs
- Render link previews with OG image (blurred overlay panel) or without (favicon-based fallback)
- Integrate link preview boxes into the social card layout, positioned above post photos
- Fetch favicons from linked domains for display in the preview
- Shorten external URLs using our URL shortener before display

## Capabilities

### New Capabilities
- `link-preview-rendering`: Standalone SVG snippet generator for external URL preview boxes, supporting two layouts (with/without OG image), blur effects, favicon fetching, and color contrast computation
- `tweet-url-processing`: Logic to classify t.co URLs (media self-reference vs external), strip redundant ones from text, expand external URLs via entities metadata, and shorten them for display

### Modified Capabilities

## Impact

- `src/features/social_cards/card_template.py` — new section for link previews above photos
- `src/features/web_browsing/twitter_status_fetcher.py` — add `entities` to API params, strip/classify URLs, pass metadata downstream
- `src/features/social_cards/` — new module(s) for link preview rendering
- `src/features/social_cards/card_layout.py` — new layout constants for link preview dimensions
- `TweetData` dataclass — new field for external link metadata
- External dependency: favicon fetching from arbitrary domains (HTTP GET)
