## 1. Image Preparation Utilities

- [x] 1.1 Add a Pillow-based helper to detect whether a static image contains transparent or semi-transparent pixels
- [x] 1.2 Add a helper to composite transparent or semi-transparent images over an opaque black background
- [x] 1.3 Ensure the helper writes an opaque image format suitable for existing upload and resize flows
- [x] 1.4 Keep opaque images unchanged when no flattening is required

## 2. Platform Photo Delivery

- [x] 2.1 Replace the private resize-only photo helper in `PlatformBotSDK` with a broader photo-preparation helper
- [x] 2.2 Preserve the under-limit JPEG fast path without downloading or re-uploading
- [x] 2.3 Download and inspect PNG, WebP, and unknown image types before returning early
- [x] 2.4 Apply black flattening before size-limit checks when transparency is present
- [x] 2.5 Reuse `resize_file` when the prepared image exceeds the active Telegram or WhatsApp photo limit
- [x] 2.6 Upload transformed or resized images once and pass the uploaded URL to platform-specific photo sends
- [x] 2.7 Preserve existing best-effort fallback behavior by logging preparation failures and returning the original URL
- [x] 2.8 Keep `send_document()` and the file/document side of media modes on the original URL path

## 3. Tests

- [x] 3.1 Update existing image utility tests to cover alpha detection and black compositing for transparent PNGs
- [x] 3.2 Add coverage for semi-transparent alpha blending over black
- [x] 3.3 Update existing platform SDK tests to verify transparent photo sends use an uploaded prepared URL
- [x] 3.4 Add coverage that opaque under-limit JPEG photo sends keep the original URL
- [x] 3.5 Add coverage that oversized prepared photos are resized before upload
- [x] 3.6 Add coverage that `file` mode sends the original URL as a document without preparation
- [x] 3.7 Add coverage that `all` mode sends a prepared photo and the original document URL
- [x] 3.8 Add coverage for preparation failure fallback to the original photo URL

## 4. Verification

- [x] 4.1 Run focused tests for image utilities and platform SDK behavior with `pipenv run pytest`
- [x] 4.2 Run `pipenv run pre-commit run --all-files --show-diff-on-failure`
