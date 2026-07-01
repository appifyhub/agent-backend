## Why

Photos sent through Telegram and WhatsApp can render transparent PNG/WebP regions unpredictably against client backgrounds. Flattening photo-mode images over black before platform delivery makes the visual result deterministic while preserving original files for document/file delivery.

## What Changes

- Add a global platform photo preparation step before Telegram `sendPhoto` and WhatsApp image sends.
- Composite transparent and semi-transparent pixels over black and send the resulting opaque image for photo delivery.
- Keep existing platform photo resizing behavior, applying resizing after any required flattening.
- Preserve original media URLs for file/document delivery.
- Ensure `all` media mode sends a black-flattened photo plus the original file/document.
- Leave video delivery and video rendering out of scope.

## Capabilities

### New Capabilities

- `platform-photo-delivery`: Platform photo sends prepare images for deterministic delivery while preserving original files for document delivery.

### Modified Capabilities

## Impact

- `src/features/integrations/platform_bot_sdk.py` - update photo preparation before platform SDK send calls.
- `src/features/images/image_size_utils.py` or a nearby image utility module - add transparency detection/flattening helper if needed.
- Tests for platform photo preparation and media-mode behavior.
- No database migration, API schema change, or new dependency expected.
