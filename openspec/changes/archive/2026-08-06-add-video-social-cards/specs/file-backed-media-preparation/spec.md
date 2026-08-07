## Purpose

Provide bounded, file-backed acquisition, processing, and persistence for remote media so large source files do not become complete Python byte buffers and temporary artifacts are always reclaimed.

## ADDED Requirements

### Requirement: Remote media is acquired through files
The system SHALL stream remote photos, poster frames, animated GIFs, videos, avatars, and link-preview images into scoped temporary files when they are prepared for social-card rendering or outbound chat delivery. The system MUST NOT accumulate a complete remote source file in a Python byte buffer before writing it to disk.

#### Scenario: Large video acquisition
- **WHEN** the system acquires a large remote video for rendering or delivery
- **THEN** it writes the response incrementally to a temporary file and provides a path to downstream processing

#### Scenario: Photo acquisition
- **WHEN** the system acquires a remote photo or poster frame for social-card rendering
- **THEN** it writes the response incrementally to a temporary file instead of retaining the complete compressed image as a Python byte buffer

### Requirement: Media processing uses file-backed inputs and outputs
The system SHALL pass local paths or file streams between download, inspection, resizing, static rendering, video composition, and attachment persistence boundaries. Complete source-media payloads MUST NOT be copied into Python byte buffers between those stages.

#### Scenario: Outbound photo preparation
- **WHEN** a downloaded photo requires background composition or resizing before delivery
- **THEN** every preparation stage reads a file-backed input and produces either the same path or another temporary path

#### Scenario: Social-card video composition
- **WHEN** one or more videos are composed into a social card
- **THEN** the compositor reads source paths and writes the composed result to a temporary output path

### Requirement: Attachment persistence accepts file-backed content
The attachment persistence boundary SHALL accept a local path or readable stream and persist it without first reading the complete file into a Python byte buffer. File-backed persistence SHALL resolve the same attachment size, MIME type, extension, URI, and remote-source metadata as byte-backed persistence.

#### Scenario: Persist prepared video
- **WHEN** a prepared video path is saved as a chat attachment
- **THEN** storage consumes the path or its stream directly and records metadata equivalent to the existing byte-backed save behavior

#### Scenario: Preserve existing byte-backed callers
- **WHEN** an existing caller saves bounded in-memory content
- **THEN** the existing byte-backed attachment behavior remains supported

#### Scenario: Materialize remotely stored attachment
- **WHEN** a remotely stored attachment is copied to a temporary path for processing or delivery
- **THEN** storage streams the attachment into that path without first constructing a complete Python byte buffer

### Requirement: Temporary media is always cleaned up
The system SHALL delete downloaded sources and every distinct derived temporary file after the owning operation completes. Cleanup MUST occur after success, handled failure, or unexpected failure and MUST NOT delete a caller-owned or persisted source.

#### Scenario: Successful operation cleanup
- **WHEN** media preparation and persistence succeed
- **THEN** all operation-owned temporary files are deleted after the final consumer finishes

#### Scenario: Failed operation cleanup
- **WHEN** downloading, processing, rendering, persistence, or delivery raises an error
- **THEN** all operation-owned temporary files created before the error are deleted

#### Scenario: Reused path cleanup
- **WHEN** a preparation stage returns its input path unchanged
- **THEN** cleanup deletes that operation-owned file exactly once

### Requirement: Existing outbound media behavior is preserved
Moving outbound photo and video preparation to file-backed persistence SHALL preserve platform size constraints, format preparation, captions, thumbnails, delivery-mode behavior, and document fallbacks.

#### Scenario: Existing photo delivery
- **WHEN** a photo is sent through any existing media mode
- **THEN** the same native-photo and document behavior occurs after file-backed preparation

#### Scenario: Existing video delivery
- **WHEN** a video is sent through any existing media mode
- **THEN** the same native-video preparation and document fallback behavior occurs after file-backed persistence
