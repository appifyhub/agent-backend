## Purpose

Exposes Seedream 5 Pro as a selectable Replicate model for text-to-image and reference-guided generation through the unified image workflow.

## ADDED Requirements

### Requirement: Seedream 5 Pro catalog availability
The external tool catalog SHALL expose `bytedance/seedream-5-pro` as `ByteDance: SeeDream 5 Pro` under the Replicate provider for the existing `images_gen` purpose. The model SHALL support at most 10 ordered reference images and SHALL be selectable without changing any intelligence-preset default.

#### Scenario: Model appears in the image tool catalog
- **WHEN** a consumer requests the available external image tools
- **THEN** Seedream 5 Pro is returned as a Replicate `images_gen` model with a 10-reference-image limit

#### Scenario: Existing presets remain authoritative
- **WHEN** image generation resolves a model from an intelligence preset without an explicit Seedream 5 Pro selection
- **THEN** the preset continues to resolve its existing image model

### Requirement: Seedream 5 Pro request mapping
Seedream 5 Pro requests SHALL send only the documented `prompt`, `image_input`, `size`, `aspect_ratio`, and `output_format` fields. Text-only requests SHALL omit `image_input`; reference-guided requests SHALL provide the first resolved images up to the model's 10-image limit. The existing PNG output default SHALL be preserved.

#### Scenario: Text-to-image request
- **WHEN** Seedream 5 Pro is selected without reference images
- **THEN** the Replicate request contains the prompt and normalized output options and omits `image_input`

#### Scenario: Reference-guided request within the limit
- **WHEN** Seedream 5 Pro is selected with between 1 and 10 resolved reference images
- **THEN** the Replicate request supplies those image URLs through `image_input` in their resolved order

#### Scenario: Reference-guided request exceeds the limit
- **WHEN** Seedream 5 Pro is selected with more than 10 resolved reference images
- **THEN** the existing unified image workflow supplies the first 10 images and reports the remaining images as ignored

#### Scenario: Undocumented unified fields are present
- **WHEN** the unified image parameters contain fields that Seedream 5 Pro does not accept
- **THEN** those fields are omitted from the Replicate request

### Requirement: Seedream 5 Pro output normalization
The unified image workflow SHALL pass 1K and 2K output requests to Seedream 5 Pro unchanged and SHALL map a 4K request to the model's maximum 2K output. It SHALL use the existing shared image aspect-ratio set, and SHALL use `match_input_image` only when reference images are present.

#### Scenario: Supported output size
- **WHEN** Seedream 5 Pro receives a 1K or 2K request
- **THEN** the same size is sent to Replicate

#### Scenario: Oversized output request
- **WHEN** Seedream 5 Pro receives a 4K request
- **THEN** the request is sent to Replicate as 2K and accounting uses the 2K output tier

#### Scenario: Ratio outside the shared set
- **WHEN** Seedream 5 Pro receives an aspect ratio outside the shared image set, such as `21:9`
- **THEN** the existing closest-supported-ratio fallback resolves it, matching every other image model

#### Scenario: Input-matched reference output
- **WHEN** Seedream 5 Pro receives reference images and the aspect ratio is omitted or explicitly set to `match_input_image`
- **THEN** the request uses `match_input_image`

#### Scenario: Input matching without a reference
- **WHEN** Seedream 5 Pro receives `match_input_image` without any reference image
- **THEN** the unified image workflow uses its existing text-to-image default aspect ratio instead

### Requirement: Seedream 5 Pro credit pricing
Successful Seedream 5 Pro output SHALL be estimated, recorded, and deducted at 4.5 credits for 1K or 9 credits for 2K, where one credit equals one US dollar cent. A 4K request clamped to 2K SHALL use the 9-credit 2K price.

#### Scenario: 1K output pricing
- **WHEN** Seedream 5 Pro successfully produces a 1K image
- **THEN** its model output cost is 4.5 credits before the existing maintenance fee

#### Scenario: 2K output pricing
- **WHEN** Seedream 5 Pro successfully produces a 2K image or a 4K request clamped to 2K
- **THEN** its model output cost is 9 credits before the existing maintenance fee

### Requirement: Existing Replicate output handling
Seedream 5 Pro's URI-array response SHALL use the existing Replicate image result extraction, persistence, asynchronous delivery, and failure handling without a model-specific output branch.

#### Scenario: Successful URI-array output
- **WHEN** a Seedream 5 Pro prediction returns a non-empty array of image URIs
- **THEN** the existing image workflow extracts the result URI and continues its normal persistence and delivery flow

#### Scenario: Empty or invalid output
- **WHEN** a Seedream 5 Pro prediction returns no usable URI
- **THEN** the existing Replicate image failure behavior handles the response
