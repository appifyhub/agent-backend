## Why

Telegram and WhatsApp convert PNG images sent as photos to JPEG, so transparent regions need an intentional background before platform delivery. The previous black-flattening behavior was removed during the attachment-storage migration; restoring that preparation step with an adaptive branded mesh background prevents arbitrary JPEG mattes and produces a better visual result.

## What Changes

- Prepare transparent outgoing PNGs sent as Telegram or WhatsApp photos with an opaque branded mesh-gradient background before photo resizing.
- Select a white or black base from the visible PNG content brightness, using the existing social-card luminance convention.
- Generate four heavily blurred, randomized palette fields using colors derived from the Agent web background and accent palette.
- Preserve original PNGs for file/document delivery, including the document half of `all` media mode.
- Leave opaque images, non-PNG files, and document delivery unchanged.

## Capabilities

### New Capabilities

- `platform-photo-delivery`: Prepares transparent PNG photos for deterministic Telegram and WhatsApp JPEG conversion while preserving original file delivery.

### Modified Capabilities

## Impact

- `src/features/integrations/platform_bot_sdk.py`: restore photo-specific preprocessing before the existing resize and attachment-save steps.
- `src/features/images/`: add focused Pillow utilities for visible-content brightness, mesh rendering, and alpha compositing.
- `test/features/images/` and `test/features/integrations/`: cover adaptive backgrounds, ordering, media-mode boundaries, and unchanged formats.
- No database migration, API schema change, or new dependency is expected.
