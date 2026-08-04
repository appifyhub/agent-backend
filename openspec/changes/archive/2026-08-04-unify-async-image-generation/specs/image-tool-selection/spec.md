## Purpose

Defines one image-model selection and one image tool purpose for both image creation and reference-image editing across settings and persistence.

## ADDED Requirements

### Requirement: Single image tool selection
The system SHALL expose one `images_gen` external-tool purpose and one nullable persisted and API-visible `tool_choice_images_gen` selection for both text-only generation and reference-image editing. The system SHALL NOT expose a separate `images_edit` purpose or `tool_choice_images_edit` setting after migration.

#### Scenario: User selects an image model
- **WHEN** a user changes their image-model selection
- **THEN** the selected model persists and resolves for both text-only and reference-image requests through the normal mapper, profile-merge, sponsorship, system-agent, and intelligence-preset paths

#### Scenario: No explicit selection
- **WHEN** no explicit image-model selection is stored
- **THEN** the applicable intelligence-preset default remains authoritative

### Requirement: Legacy image-choice precedence
The database migration SHALL copy a non-null legacy editing selection into the unified generation selection before removing the legacy column. A legacy editing selection SHALL take precedence when both legacy selections are non-null.

#### Scenario: Both legacy choices exist
- **WHEN** a persisted user has non-null generation and editing image choices
- **THEN** the unified image selection equals the former editing choice

#### Scenario: Only generation choice exists
- **WHEN** a persisted user has a generation image choice and no editing choice
- **THEN** the unified image selection retains the generation choice

#### Scenario: Only editing choice exists
- **WHEN** a persisted user has an editing image choice and no generation choice
- **THEN** the unified image selection equals the editing choice

### Requirement: Flux 1.1 retirement
Flux 1.1 Pro SHALL be removed from the external tool catalog, and persisted unified selections that refer to `black-forest-labs/flux-1.1-pro` SHALL migrate to `black-forest-labs/flux-2-pro`.

#### Scenario: Persisted Flux 1.1 selection
- **WHEN** the migration encounters a unified image selection for Flux 1.1 Pro
- **THEN** it replaces the value with Flux 2 Pro

#### Scenario: Image catalog is returned
- **WHEN** settings or profile APIs return selectable image models
- **THEN** Flux 1.1 Pro is absent and Flux 2 Pro remains available

### Requirement: Unified image usage purpose
Historical and new image-generation and image-editing usage SHALL use `images_gen` as the persisted purpose. The migration SHALL rewrite historical `images_edit` usage records to `images_gen` before the legacy purpose is removed from the application.

#### Scenario: Historical editing usage exists
- **WHEN** the migration encounters a usage record whose purpose is `images_edit`
- **THEN** the record purpose becomes `images_gen` without changing its remaining usage data

#### Scenario: Reference-image request is accounted
- **WHEN** a reference-image request records usage after migration
- **THEN** the usage purpose is `images_gen`
