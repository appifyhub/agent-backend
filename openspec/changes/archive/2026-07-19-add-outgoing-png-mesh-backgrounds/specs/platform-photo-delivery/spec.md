## ADDED Requirements

### Requirement: Adaptive transparent PNG photo background
The system SHALL composite every transparent or semi-transparent PNG sent through Telegram or WhatsApp photo delivery over an opaque branded mesh background before invoking the platform photo API.

#### Scenario: Transparent PNG with light visible content
- **WHEN** a PNG containing transparency and light visible content is sent as a Telegram or WhatsApp photo
- **THEN** the delivered photo SHALL be an opaque image whose branded mesh shades a white base

#### Scenario: Transparent PNG with dark visible content
- **WHEN** a PNG containing transparency and dark visible content is sent as a Telegram or WhatsApp photo
- **THEN** the delivered photo SHALL be an opaque image whose branded mesh shades a black base

#### Scenario: Semi-transparent PNG content
- **WHEN** a PNG contains semi-transparent pixels and is sent as a Telegram or WhatsApp photo
- **THEN** those pixels SHALL be alpha-composited over the selected mesh background without thresholding their alpha values

#### Scenario: Opaque PNG
- **WHEN** a PNG without transparent or semi-transparent pixels is sent as a Telegram or WhatsApp photo
- **THEN** the system SHALL leave its pixel content unchanged by mesh preparation

#### Scenario: Non-PNG photo
- **WHEN** a JPEG, WebP, or other non-PNG image is sent as a Telegram or WhatsApp photo
- **THEN** the system SHALL leave its pixel content unchanged by mesh preparation

### Requirement: Visible-content brightness classification
The system SHALL classify transparent PNG content as light or dark from alpha-weighted visible-pixel luminance using the established `0.299 red + 0.587 green + 0.114 blue` convention and a normalized threshold of `0.5`.

#### Scenario: Transparent padding around light content
- **WHEN** a transparent PNG has light visible pixels surrounded by fully transparent padding
- **THEN** the transparent padding SHALL NOT cause the content to be classified as dark

#### Scenario: Transparent padding with hidden RGB values
- **WHEN** fully transparent pixels contain arbitrary hidden RGB values
- **THEN** those hidden values SHALL NOT affect the light-or-dark classification

#### Scenario: Fully transparent PNG
- **WHEN** a PNG has no visible pixels
- **THEN** the system SHALL use the black-base fallback

### Requirement: Branded randomized mesh composition
The system SHALL construct each PNG background from all four configured Agent palette colors as heavily blurred fields distributed across the four quadrants with bounded randomized placement and ordering.

#### Scenario: Mesh palette
- **WHEN** the system prepares a transparent PNG photo
- **THEN** the background SHALL use the indigo, burgundy, coral, and warm amber palette fields over the selected base

#### Scenario: Inward field placement
- **WHEN** the system positions the four mesh fields
- **THEN** their nominal centers SHALL be moved inward from the quadrant centers while remaining distributed across distinct quadrants

#### Scenario: Smooth field transitions
- **WHEN** the mesh background is rendered
- **THEN** its fields SHALL overlap with sufficient blur that hard edges, quadrant seams, and distinct circle boundaries are not visible

#### Scenario: Light-base intensity
- **WHEN** the selected base is white
- **THEN** the mesh SHALL use restrained color intensity so white remains the dominant background

#### Scenario: Dark-base blur
- **WHEN** the selected base is black
- **THEN** the mesh SHALL use stronger blur than the light-base treatment so individual fields remain indistinct

### Requirement: Photo preparation precedes resizing
The system SHALL apply any required PNG mesh compositing before enforcing the active Telegram or WhatsApp photo size limit.

#### Scenario: Prepared PNG exceeds platform limit
- **WHEN** mesh compositing produces an image larger than the active platform photo limit
- **THEN** the system SHALL resize the prepared opaque image before saving and delivering it

#### Scenario: Prepared PNG is within platform limit
- **WHEN** mesh compositing produces an image within the active platform photo limit
- **THEN** the system SHALL save and deliver the prepared opaque image without dimension reduction

### Requirement: Original file delivery remains unchanged
The system SHALL restrict mesh preparation to photo delivery and preserve original media for file/document delivery.

#### Scenario: File media mode
- **WHEN** a transparent PNG is sent with media mode `file`
- **THEN** the system SHALL send the original PNG as a document without mesh compositing

#### Scenario: All media mode
- **WHEN** a transparent PNG is sent with media mode `all`
- **THEN** the system SHALL send a mesh-composited opaque photo and the original PNG document

#### Scenario: Document thumbnail preparation
- **WHEN** an image is prepared only as a document thumbnail
- **THEN** the system SHALL NOT apply the outgoing PNG mesh background to that thumbnail
