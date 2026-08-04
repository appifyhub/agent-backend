## Purpose

Keeps generic media processing focused on analysis while directing all image creation and editing through the unified image-generation contract.

## ADDED Requirements

### Requirement: Analysis-only media tool
The system SHALL register the generic attachment-analysis LLM tool as `analyze_attachments`. It SHALL accept attachment IDs, external URLs, and optional task context, and SHALL NOT accept an operation, aspect ratio, or output size.

#### Scenario: Analyze supplied media
- **WHEN** the LLM calls `analyze_attachments` with supported attachments or URLs
- **THEN** the system returns the established image-analysis, audio-transcription, or document-search result for those inputs

#### Scenario: Editing intent
- **WHEN** the partner asks for supplied images to influence a generated output
- **THEN** the LLM tool contract directs that request to `generate_image` with reference images rather than `analyze_attachments`

### Requirement: Legacy media-processing contract removal
The system SHALL remove the `process_media` LLM tool name, its `operation` argument, and its `image-edit` operation after the unified image tool is registered.

#### Scenario: Available LLM tools are enumerated
- **WHEN** the chat agent builds its tool registry
- **THEN** `analyze_attachments` and unified `generate_image` are present while `process_media` is absent
