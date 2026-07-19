## Context

`PlatformBotSDK.send_photo()` is the shared Telegram and WhatsApp photo-delivery boundary. `prepare_outgoing_attachment()` currently downloads the source, resizes it when necessary, and stores the resulting bytes internally. A prior change flattened transparent photos over black before resizing, but that helper and call were removed when outbound media moved to internal attachment storage.

Telegram and WhatsApp convert PNGs sent through their photo APIs to JPEG. The application must therefore produce an opaque result before resizing and delivery. File/document mode must continue to preserve the original PNG and its transparency.

The Agent web source defines the relevant palette family: body indigo, burgundy, coral, and warm amber. The accepted previews use fields moved inward from the quadrant centers, a lighter treatment over white, and stronger blur—especially over black.

## Goals / Non-Goals

**Goals:**

- Restore photo-only alpha compositing at the shared platform boundary.
- Replace the fixed black matte with an adaptive branded mesh for transparent PNGs.
- Choose white or black from the visible PNG content brightness.
- Apply the mesh before the existing resize step.
- Preserve original media for document delivery and the document half of `all` mode.
- Bound processing cost for large source images and avoid new dependencies.

**Non-Goals:**

- Changing generated or edited image output before it reaches platform delivery.
- Decorating opaque PNGs, JPEGs, WebP files, document thumbnails, or document delivery.
- Changing media-mode settings, platform APIs, storage models, or public API docs.
- Persisting preview assets or introducing user-configurable palettes.

## Decisions

### Prepare only explicit photo delivery

`send_photo()` will explicitly request PNG background preparation from `prepare_outgoing_attachment()`. The default path used by documents and document thumbnails will not request it.

This flag is separate from `should_resize`: document thumbnails currently resize through the same method, so treating every resized attachment as a photo would decorate thumbnails unintentionally. Telegram and WhatsApp still share one preparation path because both platforms exhibit the same JPEG conversion behavior.

### Detect PNG and transparency from decoded bytes

The helper will inspect the downloaded image with Pillow, use the decoded image format rather than the URL or temporary-file suffix, and transform only PNG images with at least one alpha value below 255. Opaque PNGs and other formats return the original path unchanged.

This avoids false decisions from extensionless internal attachment URLs and limits the new behavior to the requested format. Semi-transparent pixels are composited normally rather than thresholded.

### Classify visible content with alpha-weighted luminance

The helper will downsample the RGBA image for bounded analysis, ignore fully transparent pixels, and compute alpha-weighted mean luminance using the existing social-card coefficients:

`(0.299 * red + 0.587 * green + 0.114 * blue) / 255`

A mean above `0.5` is light and selects a white base; otherwise it selects black. Ignoring transparent padding makes the classification describe the PNG contents rather than hidden RGB values. A fully transparent PNG uses the black fallback.

Reusing the formula rather than importing the social-card theme module keeps platform delivery independent of social-card rendering; the shared behavior is the luminance convention, not the feature module.

### Render a low-resolution radial mesh, then composite at source resolution

The opaque background will contain one field for each palette color:

- `#222B4E` — body-gradient indigo
- `#3F1331` — accent dark burgundy
- `#FF6C7B` — accent coral
- `#F9A892` — accent amber

The indigo and burgundy fields use brighter blue and purple brand variants so
compositing preserves their hue instead of appearing neutral gray or near-black.
The coral and amber fields keep their canonical palette values.

On a white base, coral and amber use the baseline field strength while indigo and burgundy are 30% stronger. On a black base, coral and amber are 30% weaker while indigo and burgundy are 20% stronger.

Each field starts in a different quadrant. Nominal centers are 30% from their adjacent edges—equivalent to moving 25%-quadrant centers 20% toward the image center—and receive small bounded random offsets. Color-to-quadrant assignment is shuffled so every result contains all four colors without a fixed arrangement.

The mesh is rendered on a bounded working canvas with elongated, randomly rotated Gaussian fields, then upscaled to the source dimensions. The anisotropic falloff creates the accepted smudged effect without erasing separation between the fields. Light-content images use lower field opacity over white. Dark-content images use stronger, wider fields over black so individual shapes remain soft. The original RGBA image is then alpha-composited over the mesh and converted to opaque RGB PNG.

Rendering the mesh at bounded resolution avoids field-generation cost scaling with multi-megapixel inputs while preserving a smooth final background. Direct Gaussian fields also avoid seams from constructing four hard-edged rectangles before blur.

### Transform before resizing and save once

`prepare_outgoing_attachment()` will use the transformed path as input to `resize_file()`. The final opaque or resized bytes are saved once through the existing attachment service. Temporary source, mesh-composited, and resized paths are each passed to the existing idempotent safe-deletion helper; shared paths are harmless.

This ordering enforces Telegram and WhatsApp limits against the actual prepared image and prevents resizing alpha edges before compositing.

### Keep randomization local and testable

Mesh generation will use standard-library random functions behind module-level helpers/constants. Focused tests will patch randomness only where stable preprocessing assertions require it; production sends remain randomized. The visual mesh appearance will be verified through its implementation constants and manual preview rather than brittle pixel-perfect tests.

## Risks / Trade-offs

- [Random results make pixel-exact tests brittle] → Avoid pixel-perfect visual tests and assert only delivery invariants.
- [Very smooth gradients may band after platform JPEG conversion] → Use oversized overlapping fields and high-quality resizing; avoid visible hard boundaries and excessive synthetic noise that would worsen JPEG size.
- [Brightness near the threshold may choose an unexpected base] → Keep the established `0.5` threshold and cover boundary behavior explicitly.
- [Large PNGs add processing time] → Downsample luminance analysis and render blur on a bounded working canvas before upscaling.
- [The attachment-storage migration removed the prior matte behavior] → Restore preparation at the current internal-attachment boundary and add an ordering regression test.

## Migration Plan

No data migration is required. Deploy the code and tests together; rollback restores the current behavior where transparent PNG photos reach the platform without an application-provided matte.

## Open Questions

None.
