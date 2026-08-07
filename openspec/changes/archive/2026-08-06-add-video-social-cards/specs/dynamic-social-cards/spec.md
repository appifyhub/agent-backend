## Purpose

Render playable media from a social post inside the existing themed card while preserving explicit static rendering, deterministic media layout, bounded playback, and reliable chat delivery.

## ADDED Requirements

### Requirement: Social-card callers can select the output mode
The social-card tool SHALL accept an optional mode with `image`, `video`, or omitted values. An omitted mode SHALL select video output when the main post contains playable video or animated GIF media and image output otherwise.

#### Scenario: Automatic dynamic output
- **WHEN** mode is omitted and the main post contains playable video or animated GIF media
- **THEN** the system attempts to produce a video card

#### Scenario: Automatic static output
- **WHEN** mode is omitted and the main post contains no playable dynamic media
- **THEN** the system produces an image card

#### Scenario: Forced image output
- **WHEN** mode is `image` and the post contains video or animated GIF media
- **THEN** the system produces an image card using each dynamic item's poster image

#### Scenario: Requested video without dynamic media
- **WHEN** mode is `video` and the main post contains no playable dynamic media
- **THEN** the system produces an image card rather than failing

### Requirement: Providers preserve dynamic media identity
The platform-neutral post representation SHALL associate each dynamic media item with its playable source and poster image as one item. A provider SHALL NOT emit the poster belonging to a video or animated GIF as an additional photo.

#### Scenario: X video variants
- **WHEN** X returns compatible MP4 playback variants and a preview image for a video
- **THEN** the provider selects the highest-quality compatible variant as the playable source and retains the preview on the same video item

#### Scenario: X animated GIF variants
- **WHEN** X returns a playable animated GIF representation and preview image
- **THEN** the provider retains them as one animated GIF item

#### Scenario: Actual photo alongside video
- **WHEN** a platform identifies a photo as an independent media item alongside a video
- **THEN** the photo remains eligible for the photo section without being mistaken for the video's poster

### Requirement: Only main-post media drives dynamic rendering
Only playable media directly attached to the requested main post SHALL influence automatic dynamic output or participate in the dynamic timeline. Media inside a quoted, replied-to, or otherwise embedded post SHALL remain a static poster inside the embedded-post design.

#### Scenario: Embedded video only
- **WHEN** the main post has no dynamic media and its embedded post contains a video
- **THEN** automatic mode produces an image card with a static embedded video preview

#### Scenario: Main and embedded videos
- **WHEN** the main post and embedded post both contain videos
- **THEN** only the main post's video participates in the card timeline

### Requirement: Static and dynamic output share card geometry
The card layout SHALL produce the canvas dimensions and media placements used by both static rendering and dynamic composition. Each placement SHALL identify its media item, bounds, and corner radii so dynamic overlays align exactly with their poster images.

#### Scenario: Video overlay alignment
- **WHEN** a video card is composed from a rendered static base
- **THEN** each moving image occupies the same bounds and rounded shape as its poster in the static base

#### Scenario: Static-only rendering
- **WHEN** an image card is requested
- **THEN** the same layout result renders the card without requiring a separate geometry calculation

### Requirement: Main-post media follows deterministic layout rules
Dynamic items SHALL appear first within the existing media section after post text and link previews. Each dynamic item SHALL occupy the full inner content width while respecting card padding, SHALL be stacked vertically, and SHALL use rounded corners. Independent photos SHALL appear below all dynamic items and retain the existing photo-tiling behavior.

#### Scenario: Mixed video and photos
- **WHEN** a main post contains one video and multiple independent photos
- **THEN** the rounded video occupies the padded full-width first media row and the photos use the existing tiled layout below it

#### Scenario: Multiple dynamic items
- **WHEN** a main post contains multiple videos or animated GIFs
- **THEN** each item occupies a separate padded full-width row in source order

### Requirement: Dynamic media plays sequentially
Main-post videos and animated GIFs SHALL play sequentially in source order. Before its turn, an item SHALL show its poster image; while active, its moving image SHALL replace that poster; after it finishes, its last frame SHALL remain visible. Only the active video SHALL contribute audio, and animated GIFs SHALL always be silent.

#### Scenario: Two videos
- **WHEN** a card contains two playable videos
- **THEN** the first video plays with its audio and freezes before the second video begins playing with its audio

#### Scenario: Video without audio
- **WHEN** the active video has no audio stream
- **THEN** its timeline segment is silent and playback continues normally

#### Scenario: Animated GIF
- **WHEN** an animated GIF reaches its turn
- **THEN** it plays silently once and freezes on its final frame

### Requirement: Dynamic card duration is bounded
The complete sequential timeline SHALL stop at the configured social-card video duration limit, whose default SHALL be 120 seconds. The limit SHALL apply to the accumulated card timeline rather than separately to each media item.

#### Scenario: Timeline below the limit
- **WHEN** the combined dynamic duration is shorter than the configured limit
- **THEN** the output ends when the final dynamic item finishes

#### Scenario: Timeline exceeds the limit
- **WHEN** the accumulated timeline reaches the configured limit during an active item
- **THEN** the output ends at the limit without starting any later item

### Requirement: Dynamic rendering falls back to a usable image
If playable media cannot be downloaded, inspected, or composed, the system SHALL produce the themed image card with available poster images whenever static rendering remains possible. A failed dynamic attempt MUST NOT prevent delivery of the static result.

#### Scenario: Playback source unavailable
- **WHEN** a video poster is available but its playable source cannot be downloaded
- **THEN** the system produces and delivers the image card containing the poster

#### Scenario: Composition failure
- **WHEN** dynamic composition fails after the static base has been rendered
- **THEN** the system delivers the static base as an image card

### Requirement: Delivery follows the actual rendered output
The rendered-card result SHALL identify whether its persisted output is an image or video. Chat delivery SHALL use native photo behavior for an image result and native video behavior for a video result while retaining the user's existing media-mode fallbacks.

#### Scenario: Successful video card
- **WHEN** dynamic composition and persistence succeed
- **THEN** the card is delivered through the platform video path

#### Scenario: Static fallback result
- **WHEN** requested or automatic video rendering returns an image fallback
- **THEN** the card is delivered through the platform photo path
