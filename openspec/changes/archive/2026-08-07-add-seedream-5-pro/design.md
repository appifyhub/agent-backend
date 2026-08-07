## Context

See `proposal.md` for motivation and `specs/seedream-5-pro-image-generation/spec.md` for the behavior contract. The current unified image workflow already resolves Replicate credentials, limits ordered references from each model's `max_input_images`, maps common image arguments into `UnifiedImageParameters`, runs Replicate asynchronously, accounts by normalized output size, and extracts the first usable URI from array output.

Replicate image requests are produced from a broad unified parameter object. Seedream 4.5 has an explicit allowlist because sending the entire unified object would include fields outside its provider schema. Seedream 5 Pro likewise accepts only `prompt`, `image_input`, `size`, `aspect_ratio`, and `output_format`. The shared image tool currently exposes sizes through 4K and aspect ratios through 16:9, while Seedream 5 Pro supports only 1K/2K output and additionally supports 21:9.

## Goals / Non-Goals

**Goals:**

- Add Seedream 5 Pro through the existing Replicate image path with exact catalog metadata, documented request fields, reference capacity, size normalization, ratios, and credit prices.
- Keep model-specific behavior isolated in the existing catalog and image-parameter mapping layers.
- Verify application-owned catalog and mapping behavior with existing offline test files.

**Non-Goals:**

- Changing image intelligence-preset defaults or migrating existing selections.
- Adding output-format selection to the LLM tool; the unified workflow continues to request PNG.
- Adding a new provider branch, output extractor, background workflow, credential, database column, or dependency.
- Introducing model-specific prompt rewriting or truncation; the existing prompt-enhancement and provider-validation behavior remains in place.

## Decisions

### 1. Register Seedream 5 Pro as another unified Replicate image model

Add one external-tool definition beside Seedream 4 and 4.5 with the Replicate model ID, established `ByteDance: SeeDream ...` display-name pattern, `images_gen` type, 10-reference limit, and 4.5/9-credit output pricing. Include it in the external-tool catalog but not in any intelligence preset.

Changing the highest-price preset was rejected because its current image model costs 15 credits at both 1K and 2K, while Seedream 5 Pro costs 4.5 and 9 credits. No persistence migration is needed because image selections already store catalog IDs as nullable strings.

### 2. Give Seedream 5 Pro an exact Replicate parameter allowlist

Add an allowlist containing only `prompt`, `image_input`, `size`, `aspect_ratio`, and `output_format`. This follows the Seedream 4.5 pattern and prevents unrelated unified defaults such as inference steps, safety controls, quality, or alternate image-input field names from reaching a strict provider schema.

Allowing all non-null unified fields was rejected because it would couple this model to parameters it does not document. A separate generator branch was rejected because request creation, polling, output extraction, persistence, delivery, and accounting are already shared.

### 3. Normalize size at the shared mapping boundary

Seedream 5 Pro receives normalized 1K and 2K values directly. A 4K request is replaced with 2K before preflight and worker handoff, so both provider input and accounting reflect the actual output tier. The catalog may retain a defensive 9-credit 4K estimate, but normal execution accounts the clamped 2K value.

Seedream 5 Pro keeps the shared image aspect-ratio set. Its documented `21:9` ratio is deliberately not exposed, because a per-model ratio set would add a branch to the shared resolver for one rarely requested ratio; a `21:9` request resolves through the existing closest-supported-ratio fallback like any other unsupported ratio.

Clamping was chosen over rejecting 4K because the unified image contract already advertises 4K independently of the selected model.

### 4. Preserve the existing output and prompt paths

The unified output format remains PNG, so the existing `output_format` default is passed through the allowlist. Replicate's URI-array output is already supported by the shared extraction function and needs no Seedream-specific branch or test duplication.

The existing prompt pipeline continues to require non-empty input, enhance it before background execution, and let Replicate enforce the model's 4000-character provider limit. Application-side truncation was rejected because silently discarding enhanced prompt content would alter user intent, while a new cross-model prompt-length contract is outside this catalog addition.

## Risks / Trade-offs

- [Seedream 5 Pro's provider schema changes] → Keep its accepted fields in one explicit allowlist and update focused mapping tests when Replicate changes the contract.
- [A user specifically wants Seedream 5 Pro's native 21:9 output] → Accept the closest-ratio fallback to `16:9`; revisit a per-model ratio set only if live usage demonstrates a need.
- [An enhanced prompt exceeds the provider's 4000-character limit] → Preserve existing structured background failure notification rather than silently truncating; reconsider common prompt limits separately if live usage demonstrates a need.
- [Application rollback leaves persisted Seedream 5 Pro selections] → The resolver ignores an unknown catalog ID and falls back through the existing default and eligible-tool order; no destructive data rollback is needed.

## Migration Plan

1. Deploy the catalog definition, exact parameter allowlist, size normalization, and focused tests together.
2. No database or dependency migration is required.
3. Rollback removes the catalog and mapping entries; persisted selections safely follow the resolver's existing unknown-ID fallback until the model is available again or a user chooses another model.
