## Why

The unified image workflow does not currently expose ByteDance's Seedream 5 Pro model, so partners cannot select its 1K/2K text-to-image and reference-guided generation through Replicate. Adding it extends the existing image catalog without introducing a new provider or changing the image-generation contract.

## What Changes

- Add `bytedance/seedream-5-pro` to the Replicate external-tool catalog as `ByteDance: SeeDream 5 Pro` for the existing `images_gen` purpose.
- Support the model's documented `prompt`, `image_input`, `size`, `aspect_ratio`, and `output_format` inputs through the unified image parameter adapter, keeping the shared image aspect-ratio set.
- Support up to 10 ordered reference images and retain the existing first-N reference selection behavior.
- Pass 1K and 2K requests directly and clamp the unified workflow's unsupported 4K request to Seedream 5 Pro's maximum 2K output.
- Price successful 1K output at 4.5 credits and 2K output at 9 credits, where one credit equals one US dollar cent.
- Preserve the current intelligence-preset defaults, PNG output default, asynchronous generation flow, and Replicate array-output handling.

## Capabilities

### New Capabilities

- `seedream-5-pro-image-generation`: Seedream 5 Pro catalog exposure, documented input mapping, reference limit, output-size normalization, and credit pricing within the existing unified image workflow.

### Modified Capabilities

None.

## Impact

- Affected code: the external-tool catalog, unified Replicate image parameter mapping, and the LLM-facing image aspect-ratio options.
- Affected tests: existing external-tool catalog and image parameter utility tests.
- No database migration, dependency update, new provider credential, API schema change, intelligence-preset change, or output-processing change is required.
