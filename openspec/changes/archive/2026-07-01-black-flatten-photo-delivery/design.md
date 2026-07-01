## Context

`PlatformBotSDK.send_photo()` is the shared entry point for outbound photo delivery. It currently calls a private resize helper, then dispatches to Telegram `send_photo` or WhatsApp `send_photo`. `smart_send_photo()` routes media modes through the same boundary: `photo` uses `send_photo`, `file` uses `send_document`, and `all` sends both.

The resize helper currently uses a fast `HEAD`/`Content-Length` path and returns the original URL when an image is already under the platform limit. That is correct for size handling, but insufficient for transparent PNG/WebP delivery because transparency is a pixel-level property. A transparent image under the size limit still needs inspection and flattening before photo delivery.

## Goals / Non-Goals

**Goals:**

- Apply black-background alpha flattening to all static images delivered through `PlatformBotSDK.send_photo()`.
- Preserve current Telegram and WhatsApp photo size limits.
- Preserve file/document delivery exactly: file mode and the document half of all mode continue using the original URL.
- Avoid new dependencies by using Pillow, which is already present.
- Keep platform-specific SDK APIs focused on protocol calls rather than shared image preparation.

**Non-Goals:**

- Adding video delivery or video rendering.
- Changing image generation, image editing, or social-card rendering output.
- Changing chat settings, media mode values, database schema, or public API docs.
- Adding support for animated media beyond existing photo-delivery behavior.

## Decisions

### Centralize preparation in PlatformBotSDK

Photo preparation will live in `PlatformBotSDK` or a helper it owns, before dispatching to Telegram or WhatsApp SDKs.

**Why**: `PlatformBotSDK.send_photo()` is the only shared photo-send boundary used by generated images, edited images, social cards, and other app-level photo sends. This gives global behavior without duplicating logic in Telegram and WhatsApp wrappers.

**Alternatives considered**:

- Platform-specific SDK changes. Rejected because it duplicates identical image preparation and pushes shared behavior into protocol wrappers.
- Social-card-only preparation. Rejected because the desired behavior applies to all photos sent through platform SDKs.

### Combine flattening with the existing resize path

The existing private resize helper should become a broader photo-preparation helper. It will determine the platform max size, download image bytes when inspection or resizing is needed, flatten transparency if present, resize if the prepared image exceeds the platform limit, then upload only when the image was transformed or resized.

JPEG images under the platform limit can keep the current fast path because JPEG has no alpha channel. PNG, WebP, and unknown image types need content inspection before returning early, even if `Content-Length` is below the limit.

**Alternatives considered**:

- Always download every photo. Rejected because it adds unnecessary latency for common under-limit JPEGs.
- Run flattening as a separate upload before resizing. Rejected because it can upload twice and makes size-limit enforcement harder to reason about.

### Flatten by compositing over black

Transparent and semi-transparent pixels will be composited over an opaque black background using Pillow. The resulting delivery image will have no alpha channel.

**Why**: This matches the desired visible result. Merely changing RGB values behind transparent pixels while keeping alpha would still let Telegram or WhatsApp clients choose the visual background.

**Alternatives considered**:

- Preserve alpha and set hidden RGB values to black. Rejected because clients could still render transparent areas over non-black backgrounds.
- Use a white or theme-derived matte. Rejected because the requested matte is black and the behavior should be deterministic.

### Preserve original URL for document delivery

`smart_send_photo(file)` will continue to call `send_document()` with the original URL. `smart_send_photo(all)` will send the prepared photo first, then call `send_document()` with the original URL.

**Why**: Users choose file mode when they want the original asset. Photo delivery is optimized for platform display; document delivery should preserve the file.

### Keep failure behavior close to current delivery behavior

If preparation cannot inspect or transform an image, the system should preserve current behavior by logging the preparation failure and sending the original URL instead of blocking delivery. If photo delivery itself fails in `smart_send_photo(photo)`, the existing fallback to document delivery remains unchanged.

**Why**: The current resize helper is best-effort and returns the original URL on preparation failure. Keeping this behavior avoids turning image-processing edge cases into failed chat responses.

## Risks / Trade-offs

- More image downloads for alpha-capable formats: PNG/WebP photos under the size limit now need inspection. Mitigation: keep the JPEG fast path and only inspect formats that can carry alpha or cannot be identified safely.
- Animated GIF/WebP ambiguity: flattening animated media can collapse it to a single frame. Mitigation: keep animated media behavior out of scope and avoid adding special animated-media handling in this change.
- Upload provider dependency for transformed under-limit images: transparent images now need re-upload even if they are small. Mitigation: this is required to send an opaque prepared image URL through existing platform APIs.
- Best-effort fallback can leave rare unprocessable transparent images unchanged. Mitigation: log failures and keep tests focused on supported static image formats.
