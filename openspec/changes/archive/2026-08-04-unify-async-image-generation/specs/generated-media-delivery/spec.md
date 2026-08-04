## Purpose

Provides accurate upload status when completed generated media enters platform preparation and delivery.

## ADDED Requirements

### Requirement: Result-ready generated-media upload actions
After an image or video provider result is ready, the detached worker SHALL request the media-specific upload action immediately before calling the corresponding smart sender. The action SHALL precede SDK download, resizing or transcoding, persistence, and platform upload work. Telegram SHALL forward the action, while WhatsApp SHALL retain its no-op behavior.

#### Scenario: Image delivery preparation starts
- **WHEN** an image result is ready for delivery
- **THEN** the worker requests `upload_photo` immediately before `smart_send_photo`

#### Scenario: Video delivery preparation starts
- **WHEN** a video result is ready for delivery
- **THEN** the worker requests `upload_video` immediately before `smart_send_video`

#### Scenario: WhatsApp generated-media delivery starts
- **WHEN** a completed image or video is ready for WhatsApp delivery
- **THEN** the unsupported upload action causes no failure and delivery preparation proceeds
