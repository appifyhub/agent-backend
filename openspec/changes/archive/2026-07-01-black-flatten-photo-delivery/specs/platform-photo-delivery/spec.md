## ADDED Requirements

### Requirement: Global photo delivery preparation
The system SHALL prepare every static image sent through `PlatformBotSDK.send_photo()` before invoking Telegram or WhatsApp photo/image APIs.

#### Scenario: Transparent PNG sent as photo
- **WHEN** `PlatformBotSDK.send_photo()` is called with a PNG image containing transparent pixels
- **THEN** the platform-specific photo send SHALL receive a URL for an opaque image where transparent pixels have been composited over black

#### Scenario: Semi-transparent PNG sent as photo
- **WHEN** `PlatformBotSDK.send_photo()` is called with a PNG image containing semi-transparent pixels
- **THEN** the platform-specific photo send SHALL receive a URL for an opaque image where semi-transparent pixels have been composited over black using alpha blending

#### Scenario: Opaque JPEG under platform limit
- **WHEN** `PlatformBotSDK.send_photo()` is called with an opaque JPEG whose size is within the active platform photo limit
- **THEN** the platform-specific photo send SHALL receive the original photo URL without re-uploading

### Requirement: Platform photo size limits after preparation
The system SHALL enforce the active platform photo size limit after any transparency flattening has been applied.

#### Scenario: Flattened image exceeds platform limit
- **WHEN** a transparent image is flattened over black and the prepared file exceeds the active platform photo size limit
- **THEN** the system SHALL resize the prepared file before upload and send the resized prepared image URL

#### Scenario: Opaque image exceeds platform limit
- **WHEN** an opaque image exceeds the active platform photo size limit
- **THEN** the system SHALL resize the image using the existing resize behavior before upload and send the resized image URL

#### Scenario: Prepared image is within platform limit
- **WHEN** a downloaded image is either flattened or resized and the prepared file is within the active platform photo size limit
- **THEN** the system SHALL upload that prepared file once and send the uploaded URL

### Requirement: Media mode preserves original file delivery
The system SHALL preserve original media URLs for file/document delivery while applying photo preparation to photo delivery.

#### Scenario: Photo media mode
- **WHEN** `smart_send_photo()` is called with media mode `photo`
- **THEN** the system SHALL send only the prepared photo through `send_photo()`

#### Scenario: File media mode
- **WHEN** `smart_send_photo()` is called with media mode `file`
- **THEN** the system SHALL send the original URL through `send_document()` without alpha flattening or photo preparation

#### Scenario: All media mode
- **WHEN** `smart_send_photo()` is called with media mode `all`
- **THEN** the system SHALL send a prepared photo through `send_photo()` and send the original URL through `send_document()`

### Requirement: Preparation failure preserves delivery
The system SHALL preserve existing best-effort delivery behavior when photo preparation cannot inspect, transform, resize, or upload an image.

#### Scenario: Preparation fails before platform send
- **WHEN** photo preparation fails before a platform-specific photo API call is made
- **THEN** the system SHALL log the preparation failure and attempt to send the original photo URL

#### Scenario: Photo send fallback in smart photo mode
- **WHEN** `smart_send_photo()` is called with media mode `photo` and the prepared photo send fails
- **THEN** the system SHALL fall back to sending the original URL as a document
