## ADDED Requirements

### Requirement: Social cards render from platform-neutral posts
The system SHALL render social card images from platform-neutral social post domain models owned by the social cards feature, rather than from X/Twitter-specific fetcher dataclasses.

#### Scenario: Renderer receives neutral post model
- **WHEN** a social post is rendered as a social card
- **THEN** the renderer, SVG template, and embedded-post renderer consume a platform-neutral post model instead of `TweetData`

#### Scenario: X post renders through neutral model
- **WHEN** a supported X/Twitter URL is rendered as a social card
- **THEN** the system maps the X/Twitter response into the platform-neutral post model before rendering the image

### Requirement: Social card providers isolate platform-specific fetching
The system SHALL use social post provider adapters to isolate platform-specific URL parsing, API fetching, and response mapping from the card renderer.

#### Scenario: Provider selected from URL
- **WHEN** a social post URL is submitted for card rendering
- **THEN** the orchestrator selects a provider that supports the URL before requesting platform-specific tools or fetching platform data

#### Scenario: Unsupported platform rejected
- **WHEN** a submitted social post URL is not supported by any registered provider
- **THEN** the system fails with a structured validation error and does not attempt card rendering

### Requirement: Existing X/Twitter rendering remains supported
The system SHALL preserve existing X/Twitter social card rendering behavior while moving X/Twitter-specific logic behind the provider boundary.

#### Scenario: X URL renders successfully
- **WHEN** a supported X/Twitter post URL is submitted and the configured X API tool returns valid post data
- **THEN** the system renders, stores, and sends a social card image as it did before this change

#### Scenario: X referenced post is rendered as embedded post
- **WHEN** a supported X/Twitter post includes a quoted or replied-to post that can be fetched
- **THEN** the system represents that referenced content as an embedded platform-neutral post in the rendered social card

### Requirement: Platform branding is data-driven
The system SHALL render social card source branding from platform metadata rather than hardcoded X/Twitter template logic.

#### Scenario: X card uses X branding from metadata
- **WHEN** an X/Twitter post is rendered
- **THEN** the footer uses X/Twitter platform metadata to select the appropriate logo for the current theme

#### Scenario: Renderer remains closed to new platform logos
- **WHEN** a future provider supplies different platform branding metadata
- **THEN** the renderer can display that platform branding without adding provider-specific branches to the template

### Requirement: Social card orchestration remains responsible for shared rendering workflow
The system SHALL keep shared social card workflow responsibilities in the orchestrator, including provider selection, asset resolution, theme selection, image rendering, and attachment storage.

#### Scenario: Provider returns post data only
- **WHEN** a provider fetches a social post
- **THEN** the provider returns platform-neutral post data and does not render or store the social card image

#### Scenario: Orchestrator stores rendered image
- **WHEN** rendering succeeds for a supported social post
- **THEN** the orchestrator stores the generated image as a chat attachment and returns its public URL
