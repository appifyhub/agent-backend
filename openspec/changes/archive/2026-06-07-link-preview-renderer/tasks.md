## 1. Data Model & URL Processing

- [x] 1.1 Add `TweetLinkPreview` dataclass (title, description, og_image_url, expanded_url, domain) and `link_previews` field to `TweetData`
- [x] 1.2 Add `entities` to `tweet.fields` in Twitter API request params
- [x] 1.3 Implement URL classification in `__parse_structured`: identify self-referencing media URLs vs external URLs from entities
- [x] 1.4 Strip all t.co URLs from tweet text (both media and external) during structured parsing
- [x] 1.5 Populate `link_previews` list with metadata for external URLs that have at least title or description

## 2. Link Preview Renderer (standalone)

- [x] 2.1 Create `src/features/social_cards/link_preview.py` module with layout constants (3:2 aspect ratio, overlay height, text sizes, favicon sizes)
- [x] 2.2 Implement domain shortening utility (extract subdomain.domain.tld from full URL)
- [x] 2.3 Implement favicon fetcher (GET `https://{domain}/favicon.ico`, short timeout, return bytes or None)
- [x] 2.4 Implement OG image color extraction (reuse `_dominant_from_bytes` pattern from theme.py)
- [x] 2.5 Implement with-OG-image layout: sharp image top, feGaussianBlur on clipped bottom region, 30% contrast overlay rect (bottom corners rounded), text rendering (title 2 lines bold, description 3 lines, small favicon + domain)
- [x] 2.6 Implement without-OG-image layout: fully-rounded semi-transparent rect contrasting card background, large favicon left vertically centered, text block right (title 2 lines bold, description 3 lines, small favicon + domain)
- [x] 2.7 Implement text truncation with ellipsis for title (2 lines) and description (3 lines)
- [x] 2.8 Implement multiple link previews stacking (vertical, PHOTO_GAP spacing)

## 3. Orchestrator Integration

- [x] 3.1 In `SocialCardOrchestrator.execute`: fetch OG images from `link_previews[].og_image_url` via PhotoDownloader
- [x] 3.2 In `SocialCardOrchestrator.execute`: fetch favicons for each link preview domain
- [x] 3.3 In `SocialCardOrchestrator.execute`: shorten external URLs via URL shortener (365-day expiry)
- [x] 3.4 Pass link preview data (metadata + image bytes + favicon bytes + shortened URLs) to card renderer

## 4. Card Template Integration

- [x] 4.1 Add link preview section in `build_svg` between body text and photos section
- [x] 4.2 Call link preview renderer to get SVG defs + content fragments
- [x] 4.3 Update Y cursor after link previews to maintain correct layout spacing

## 5. Testing & Validation

- [x] 5.1 Add scratchpad test function that renders cards with external-link tweets and opens results
- [x] 5.2 Verify blur effect renders correctly via resvg
- [x] 5.3 Verify fallback layout (no OG image) renders correctly
- [x] 5.4 Verify text truncation and ellipsis at boundary lengths
- [x] 5.5 Verify self-referencing URLs are stripped from tweet text
