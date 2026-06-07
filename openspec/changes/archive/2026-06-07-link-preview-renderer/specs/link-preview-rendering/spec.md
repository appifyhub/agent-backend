## ADDED Requirements

### Requirement: Link preview with OG image renders blur overlay panel

The system SHALL render a link preview box at full card inner width with a 3:2 aspect ratio OG image on top. The bottom ~40% SHALL contain an info overlay panel with a blurred copy of the image region underneath, covered by a semi-transparent rect (30% opacity) whose color contrasts to the OG image's average color. Text color SHALL contrast to the overlay color.

#### Scenario: External link with OG image and metadata
- **WHEN** a tweet contains an external URL with OG image, title, and description available from Twitter entities
- **THEN** the renderer produces an SVG snippet with the OG image cropped to 3:2, a feGaussianBlur filter on the bottom image region, a 30% opacity overlay rect with bottom corners rounded, and text content (title bold max 2 lines, description max 3 lines, small favicon + domain)

#### Scenario: OG image overlay corner radius
- **WHEN** the overlay panel is rendered on top of an OG image
- **THEN** only the bottom corners SHALL be rounded (matching photo corner radius), top corners SHALL be square since they overlap the image

### Requirement: Link preview without OG image renders favicon-based fallback

The system SHALL render a fully-rounded rect when no OG image is available. The rect SHALL be semi-transparent (30% opacity) with color contrasting to the social card's background gradient. A large favicon SHALL be placed on the left side, vertically centered against the text block. Text color SHALL contrast to the rect color.

#### Scenario: External link without OG image
- **WHEN** a tweet contains an external URL with title and description but no OG image
- **THEN** the renderer produces an SVG snippet with a fully-rounded semi-transparent rect, a large favicon on the left vertically centered, and text on the right (title bold max 2 lines, description max 3 lines, small favicon + domain on bottom line)

#### Scenario: Favicon unavailable
- **WHEN** the favicon cannot be fetched from the linked domain
- **THEN** the system SHALL use a 🌐 globe emoji as fallback, rendered via the emoji font

### Requirement: Domain display is shortened

The system SHALL display only the subdomain.domain.tld portion of the URL (e.g., "nasa.gov", "wikipedia.org"), not the full path.

#### Scenario: URL with path and query params
- **WHEN** the expanded URL is "https://www.nasa.gov/news-release/crew-13/?utm_source=twitter"
- **THEN** the displayed domain SHALL be "nasa.gov"

#### Scenario: URL with subdomain
- **WHEN** the expanded URL is "https://docs.python.org/3/library/re.html"
- **THEN** the displayed domain SHALL be "docs.python.org"

### Requirement: Text truncation with ellipsis

Title SHALL be bold, maximum 2 lines with ellipsis truncation. Description SHALL be regular weight, maximum 3 lines with ellipsis truncation.

#### Scenario: Title exceeds 2 lines
- **WHEN** the link title text would wrap beyond 2 lines at the rendered font size
- **THEN** the title SHALL be truncated at 2 lines with trailing ellipsis character

#### Scenario: Description exceeds 3 lines
- **WHEN** the link description text would wrap beyond 3 lines at the rendered font size
- **THEN** the description SHALL be truncated at 3 lines with trailing ellipsis character

### Requirement: Multiple link previews stack vertically

When multiple external links exist in a tweet, their preview boxes SHALL be stacked vertically with the same gap used between photos.

#### Scenario: Tweet with two external links
- **WHEN** a tweet text contains two external URLs with metadata
- **THEN** two link preview boxes SHALL be rendered stacked vertically with PHOTO_GAP spacing between them

### Requirement: Link previews are positioned above post photos

Link preview boxes SHALL appear in the card layout after the tweet body text and before any attached post photos.

#### Scenario: Tweet with external link and photos
- **WHEN** a tweet has both an external URL and attached photos
- **THEN** the link preview box SHALL render between the body text section and the photos section

### Requirement: Missing metadata omits preview

If no title and no description are available for an external URL, the link preview SHALL be omitted entirely.

#### Scenario: External URL with no OG metadata
- **WHEN** the Twitter API entities provide no title and no description for an external URL
- **THEN** no link preview box SHALL be rendered for that URL
