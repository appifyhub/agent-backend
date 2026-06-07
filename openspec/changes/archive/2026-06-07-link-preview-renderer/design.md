## Context

The social card system renders tweet screenshots as SVG (via `card_template.py`) then rasterizes with `resvg_py`. Tweet text currently includes raw `t.co` URLs that are either self-referencing media links (redundant) or external URLs (meaningful but ugly). The Twitter API v2 provides an `entities` field with URL expansion metadata including OG title, description, images, and unwound URLs — but we don't request it today.

## Goals / Non-Goals

**Goals:**
- Strip self-referencing t.co URLs (media links) from rendered tweet text
- Render external URLs as rich link preview cards within the social card
- Support two visual modes: with OG image (blur overlay) and without (favicon-based)
- Keep the link preview renderer as a standalone, testable component
- Maintain visual consistency with existing card elements (corner radius, padding, fonts)

**Non-Goals:**
- Rendering video previews or animated content
- Caching OG metadata beyond what Twitter API provides
- Supporting non-Twitter social card sources
- Interactive elements (the output is a static PNG)

## Decisions

### 1. Link preview as SVG snippet generator

The link preview renderer produces SVG fragment strings (defs + content) that `card_template.py` composes into the full SVG. This mirrors how photos are already handled — no new rendering pipeline.

**Alternative**: Render link previews as separate images and embed as base64. Rejected because it adds complexity and a second render pass.

### 2. Blur via feGaussianBlur on clipped image duplicate

For the overlay panel, we duplicate the OG image region, clip it to the overlay bounds, apply `feGaussianBlur`, then overlay the semi-transparent rect and text. This is the standard SVG approach and `resvg` already supports `feGaussianBlur` (we use `feDropShadow` which wraps it).

**Alternative**: CSS `backdrop-filter` — not supported in SVG/resvg.

### 3. Color computation reuses existing theme infrastructure

The overlay contrast color is computed the same way as `_accent_color` / `_contrast_text` in `card_template.py` — extract dominant color from OG image, compute contrasting overlay fill and text color. For the no-image case, contrast against `theme.gradient_start`.

### 4. Favicon fetching with graceful fallback

Fetch `https://{domain}/favicon.ico` with a short timeout. If it fails or returns non-image content, fall back to the 🌐 emoji rendered via the emoji font. Favicon is embedded as base64 in the SVG.

**Alternative**: Parse HTML for `<link rel="icon">` tags. Rejected as too complex for marginal gain — most sites serve `/favicon.ico`.

### 5. URL shortening for displayed external links

External URLs are shortened using our existing URL shortener (same as the tweet card footer URL) with 365-day expiry. The shortened URL is displayed in the preview; the original expanded URL is what was shortened.

### 6. Data flow through TweetData

Add a new `TweetLinkPreview` dataclass to hold per-link metadata (title, description, OG image URL, expanded URL, domain). `TweetData` gets a new `link_previews: list[TweetLinkPreview]` field populated during `__parse_structured`. The orchestrator fetches OG images and favicons, then passes bytes to the renderer.

## Risks / Trade-offs

- **Favicon fetch latency** → Short timeout (2s), parallel with OG image downloads via existing `PhotoDownloader`
- **Missing OG metadata** → Graceful degradation: no title/description = skip preview entirely
- **Large OG images** → We already handle image downloads for tweet photos; same size constraints apply
- **feGaussianBlur performance** → Blur is applied to a small clipped region (~40% of a 3:2 box), not the full image. Negligible render cost.
- **Twitter API rate limits** → No additional API calls needed; `entities` is part of the same tweet fetch response
