## 1. External Tool Catalog

- [x] 1.1 Add the Seedream 5 Pro Replicate tool definition with ID `bytedance/seedream-5-pro`, display name `ByteDance: SeeDream 5 Pro`, `images_gen` type, 10-reference limit, and 4.5/9-credit 1K/2K pricing, then include it in `ALL_EXTERNAL_TOOLS` without changing intelligence presets.

## 2. Image Parameter Mapping

- [x] 2.1 Add Seedream 5 Pro's exact Replicate input allowlist for `prompt`, `image_input`, `size`, `aspect_ratio`, and `output_format` so unrelated unified fields are omitted.
- [x] 2.2 Add Seedream 5 Pro size normalization that preserves 1K and 2K and maps 4K to 2K before preflight accounting and provider execution.
- [x] 2.3 Keep the shared image aspect-ratio set and closest-match behavior for Seedream 5 Pro, without advertising a model-specific `21:9` option.

## 3. Existing Test Coverage

- [x] 3.1 Update the existing image parameter utility tests to verify the exact request fields, absent `image_input` for text-only requests, ordered `image_input` for references, 1K/2K preservation, 4K-to-2K clamping, and closest-ratio fallback for unsupported ratios.

## 4. Verification

- [x] 4.1 Run Ruff and the project spacing checker with fixes on every changed Python file.
- [x] 4.2 Run the focused image-parameter and smart-image-generator test modules offline through Pipenv.
