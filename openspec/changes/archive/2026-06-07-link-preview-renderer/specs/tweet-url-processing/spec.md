## ADDED Requirements

### Requirement: Request entities from Twitter API

The system SHALL include `entities` in the `tweet.fields` API parameter when fetching tweet data.

#### Scenario: Tweet fetch includes entities
- **WHEN** the system fetches a tweet from the Twitter API v2
- **THEN** the request params SHALL include "entities" in the "tweet.fields" value

### Requirement: Strip self-referencing media URLs from text

The system SHALL remove t.co URLs from the tweet text when their expanded URL references the tweet's own media (contains `/status/{tweet_id}/photo/`).

#### Scenario: Tweet with photo attachment URL in text
- **WHEN** a tweet's text contains "Check this out https://t.co/abc123" and entities show that URL expands to "https://x.com/user/status/12345/photo/1" matching the tweet's own ID
- **THEN** the rendered text SHALL be "Check this out" with the t.co URL removed and trailing whitespace trimmed

#### Scenario: Tweet text is only a media URL
- **WHEN** the entire tweet text is just "https://t.co/abc123" which expands to the tweet's own photo
- **THEN** the rendered text SHALL be empty (the card shows only the photo)

### Requirement: Classify external URLs and extract metadata

The system SHALL identify t.co URLs that expand to external domains (not x.com/twitter.com self-references) and extract their metadata from the entities response (title, description, OG image URLs, expanded URL).

#### Scenario: Tweet with external link
- **WHEN** a tweet contains "Read more: https://t.co/xyz789" and entities show it expands to "https://www.nasa.gov/article" with title "NASA Article" and description "Space news"
- **THEN** the system SHALL produce a link preview data object with title="NASA Article", description="Space news", expanded_url="https://www.nasa.gov/article", and any OG image URLs from entities

#### Scenario: External link without metadata in entities
- **WHEN** a tweet contains a t.co URL that expands to an external domain but entities provide no title or description
- **THEN** the system SHALL not produce a link preview data object for that URL

### Requirement: Shorten external URLs for display

External URLs that produce link previews SHALL be shortened using the system's URL shortener with 365-day expiry before being displayed in the preview domain line.

#### Scenario: External URL is shortened
- **WHEN** an external link preview is being rendered
- **THEN** the URL shortener SHALL be called with the expanded URL and a 365-day validity period, and the shortened domain SHALL be displayed

### Requirement: TweetData carries link preview metadata

The `TweetData` dataclass SHALL include a field for link preview metadata, containing per-link title, description, OG image URL, expanded URL, and domain.

#### Scenario: Structured tweet data includes link previews
- **WHEN** `as_structured()` is called on a tweet with external URLs that have metadata
- **THEN** the returned `TweetData` SHALL have a populated `link_previews` list with one entry per external URL that has at least title or description

### Requirement: Tweet text retains non-media external URLs during stripping

When stripping URLs from text, the system SHALL only remove self-referencing media URLs. External t.co URLs SHALL also be removed from the display text (since they are rendered as preview boxes), but their metadata SHALL be preserved in `link_previews`.

#### Scenario: Tweet with both media and external URLs
- **WHEN** a tweet text contains one t.co URL expanding to own photo and another expanding to an external site
- **THEN** both t.co URLs SHALL be removed from the display text, the photo renders as an attachment, and the external link renders as a preview box
