## Purpose

Provides one reliable asynchronous image workflow for text-only creation and reference-image editing while preserving established provider behavior.

## ADDED Requirements

### Requirement: Unified image generation contract
The system SHALL expose one `generate_image` LLM tool for text-only image generation and reference-image editing. The tool SHALL require a prompt and SHALL accept optional comma-separated image attachment IDs and external image URLs alongside the existing optional aspect-ratio and output-size inputs.

#### Scenario: Text-only generation
- **WHEN** `generate_image` receives a prompt without reference-image attachment IDs or URLs
- **THEN** the system starts text-to-image generation with the selected image model

#### Scenario: Reference-image editing
- **WHEN** `generate_image` receives a prompt and one or more valid reference-image attachment IDs or URLs
- **THEN** the system supplies the resolved images to the same selected image model and starts reference-image editing

#### Scenario: Invalid references
- **WHEN** a supplied reference cannot be resolved or is not a supported image
- **THEN** the system returns a structured error without starting a background job

### Requirement: Existing image adapter behavior
Text-only and reference-image requests SHALL retain the established Replicate, Google AI, and xAI parameter mapping, MIME handling, input-size accounting, moderation handling, response validation, output persistence, and structured failure behavior. Reference-image requests SHALL pass short-lived public attachment URLs directly to providers and derive accounting sizes from stored attachment streams without downloading those public URLs or creating manual temporary files. The workflow SHALL use the selected model's existing `max_input_images` limit without introducing new image-model mapping rules.

#### Scenario: Provider receives reference images
- **WHEN** a valid reference-image request reaches a supported provider adapter
- **THEN** the adapter receives the same effective inputs and options as the existing image-editing flow

#### Scenario: Provider receives public attachment URLs
- **WHEN** a reference-image request reaches a supported provider adapter
- **THEN** the adapter passes its short-lived public attachment URLs directly without downloading them or creating manual temporary files

#### Scenario: Text-only provider request
- **WHEN** an image request has no references
- **THEN** the adapter retains the established text-to-image behavior for the selected provider

### Requirement: Ordered image reference limits
The workflow SHALL retain the first `max_input_images` resolved reference images in request order, omit subsequent references from provider input, and report retained and ignored reference counts in the immediate started details.

#### Scenario: References are within the selected model limit
- **WHEN** a request resolves no more references than the selected model supports
- **THEN** every resolved reference is retained and the ignored count is zero

#### Scenario: References exceed the selected model limit
- **WHEN** a request resolves more references than the selected model supports
- **THEN** the first supported number of references is retained in their original order and the remaining references are reported as ignored

### Requirement: Foreground image preparation and preflight
Before prompt enhancement or background admission, the smart image workflow SHALL prepare retained reference URLs and accounting sizes, map one `UnifiedImageParameters` value, and validate the selected image tool's minimum spend. The detached worker and simple adapter SHALL consume that prepared parameter value without remapping the request.

#### Scenario: Image request is affordable
- **WHEN** the retained references and mapped output size pass spending preflight
- **THEN** prompt enhancement and background admission may proceed with the same prepared image parameters

#### Scenario: Image request is not affordable
- **WHEN** image spending preflight fails
- **THEN** the system returns the structured preflight error without enhancing the prompt, acquiring a worker slot, or invoking an image provider

#### Scenario: Detached image adapter starts
- **WHEN** an admitted image worker constructs the simple image adapter
- **THEN** it supplies the prepared unified parameters and required reference metadata without repeating URL preparation, size resolution, or model-parameter mapping

### Requirement: Bounded asynchronous image work
The system SHALL perform admitted image generation and editing outside the chat request using background-owned dependencies, SHALL admit at most 16 in-flight image jobs per service instance, and SHALL return a started result immediately after launching an admitted job.

#### Scenario: Admitted image job
- **WHEN** validation and prompt enhancement succeed and an image worker slot is available
- **THEN** the system starts a background job and returns details instructing the chat model to tell the partner that the image will be delivered when ready

#### Scenario: Busy image service
- **WHEN** all 16 image worker slots are occupied
- **THEN** the system returns a structured busy failure without invoking an image provider

#### Scenario: Worker terminates
- **WHEN** an image worker succeeds or fails
- **THEN** the system releases its worker slot

### Requirement: Detached image execution
Background image work SHALL NOT retain the request-scoped database session. A worker SHALL reconstruct detached dependencies from captured invoker and chat identifiers. Provider accounting decorators SHALL own release of the transactions created by preflight and usage accounting; simple image and video adapters SHALL NOT own those accounting transaction boundaries. Every image provider SHALL release its active preflight transaction before external generation I/O so accounting can acquire a fresh transaction afterward.

#### Scenario: Foreground request completes
- **WHEN** `generate_image` returns its started result
- **THEN** the background worker continues without accessing the closed request session

#### Scenario: Replicate prediction is created and awaited
- **WHEN** Replicate preflight succeeds
- **THEN** the accounting decorator rolls back before creating the remote prediction
- **AND** the decorated prediction rolls back again before image waiting or video polling
- **AND** no active database transaction or checked-out connection is retained across either external boundary

#### Scenario: Synchronous provider generation
- **WHEN** Google AI or xAI preflight succeeds
- **THEN** its accounting decorator rolls back the active database transaction before the synchronous provider request begins
- **AND** usage accounting starts a fresh transaction after the provider returns

### Requirement: Asynchronous image completion
Successful background work SHALL persist the generated output and deliver it through the existing smart photo sender. Generation, persistence, preparation, or delivery failure SHALL be converted to a structured image-generation failure and sent to the originating chat through the existing system-announcement flow.

#### Scenario: Successful image delivery
- **WHEN** an image provider returns a valid output and platform delivery succeeds
- **THEN** the originating chat receives the generated or edited image according to its media preference

#### Scenario: Background image failure
- **WHEN** generation, output persistence, preparation, or platform delivery fails after the foreground request has completed
- **THEN** the originating chat receives a concise localized failure notification and the failure is logged

### Requirement: Image upload chat action
After a provider result is ready and immediately before smart photo delivery begins, the background worker SHALL request the `upload_photo` chat action. Telegram SHALL forward the action, while WhatsApp SHALL retain its no-op behavior.

#### Scenario: Telegram image delivery starts
- **WHEN** a generated image is ready for delivery to Telegram
- **THEN** the system requests `upload_photo` before invoking smart photo delivery

#### Scenario: WhatsApp image delivery starts
- **WHEN** a generated image is ready for delivery to WhatsApp
- **THEN** the unsupported chat action causes no failure and image delivery proceeds
