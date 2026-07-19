## 1. PNG Background Utilities

- [x] 1.1 Restore a focused Pillow bitmap utility module for decoded PNG-format and alpha-channel inspection
- [x] 1.2 Implement downsampled alpha-weighted visible-content luminance classification with the `0.5` threshold and fully transparent fallback
- [x] 1.3 Implement bounded-resolution four-field mesh rendering with the Agent palette, inward randomized quadrant placement, and separate light/dark opacity and blur profiles
- [x] 1.4 Composite transparent and semi-transparent PNG content over the selected mesh and write an opaque RGB PNG while returning opaque PNGs and non-PNG images unchanged

## 2. Platform Photo Delivery

- [x] 2.1 Add an explicit photo-background preparation option to `PlatformBotSDK.prepare_outgoing_attachment()` and enable it only from Telegram and WhatsApp `send_photo()` paths
- [x] 2.2 Run mesh compositing after download and before `resize_file()`, then save only the final prepared bytes through the existing attachment service
- [x] 2.3 Clean up source, composited, and resized temporary paths safely when helpers return shared paths
- [x] 2.4 Preserve original content for file/document delivery, the document side of `all` mode, and document thumbnails

## 3. Regression Tests

- [x] 3.1 Add focused bitmap utility tests for transparent PNG compositing and light/dark classification that ignores transparent padding
- [x] 3.2 Extend existing platform SDK tests to prove mesh preparation runs before resizing for Telegram and WhatsApp photo sends
- [x] 3.3 Add media-mode regression coverage proving file delivery, document thumbnails, and the document half of `all` mode retain original content

## 4. Verification

- [x] 4.1 Run `pipenv run ruff check --fix` and `pipenv run python tools/check_spacing.py --fix` on every changed Python file
- [x] 4.2 Run focused image utility and platform SDK tests with `pipenv run pytest`
- [x] 4.3 Run the full offline test suite with `pipenv run pytest`
- [x] 4.4 Run `openspec validate add-outgoing-png-mesh-backgrounds --strict`
