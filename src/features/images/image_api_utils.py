from dataclasses import asdict, dataclass, replace

from features.external_tools.external_tool import ExternalTool
from features.external_tools.external_tool_library import (
    IMAGE_GEN_EDIT_FLUX_2_MAX,
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_2,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO,
    IMAGE_GEN_EDIT_GPT_IMAGE_1_5,
    IMAGE_GEN_EDIT_GPT_IMAGE_2,
    IMAGE_GEN_EDIT_SEEDREAM_4,
    IMAGE_GEN_EDIT_SEEDREAM_4_5,
    IMAGE_GEN_GROK_IMAGINE,
    IMAGE_GEN_GROK_IMAGINE_QUALITY,
    NANO_BANANA,
    NANO_BANANA_2,
    NANO_BANANA_PRO,
)
from features.images.image_size_utils import convert_size_to_k, convert_size_to_mp, resolve_closest_aspect_ratio
from util import log

VALID_ASPECT_RATIOS = [
    "9:16",  # Ultra-tall portrait
    "2:3",   # Tall portrait
    "3:4",   # Portrait
    "1:1",   # Square
    "4:3",   # Landscape
    "3:2",   # Wide landscape
    "16:9",  # Ultra-wide landscape
]

ALLOWED_REPLICATE_PARAMS: dict[str, set[str]] = {
    IMAGE_GEN_EDIT_SEEDREAM_4_5.id: {
        "prompt", "image_input", "size", "aspect_ratio",
        "sequential_image_generation", "max_images", "disable_safety_checker",
    },
}


@dataclass(frozen = True)
class UnifiedImageParameters:
    # prompting
    prompt: str
    prompt_upsampling: bool = False
    enhance_prompt: bool = False
    # output
    aspect_ratio: str = "2:3"
    size: str = "2K"
    resolution: str | None = None
    image_size: str | None = None
    quality: str = "high"
    width: int | None = None
    height: int | None = None
    output_format: str = "png"
    output_mime_type: str = "image/png"
    output_quality: int = 90
    output_compression: int = 90
    background: str = "auto"
    # inference
    num_inference_steps: int = 30
    number_of_images: int = 1
    num_outputs: int = 1
    max_images: int = 1
    sequential_image_generation: str = "disabled"
    # safety
    moderation: str = "low"
    safety_tolerance: int = 2
    safety_filter_level: str = "block_only_high"
    disable_safety_checker: bool = True
    # search
    google_search: bool = False
    image_search: bool = False
    # input
    input_fidelity: str = "high"
    guidance_scale: float = 5.5
    # image inputs (URLs)
    image: str | None = None
    input_image: str | None = None
    image_input: list[str] | None = None
    input_images: list[str] | None = None


def map_to_model_parameters(
    tool: ExternalTool,
    prompt: str = "",
    aspect_ratio: str | None = None,
    output_size: str | None = None,
    input_urls: list[str] | None = None,
) -> UnifiedImageParameters:
    log.d(f"Mapping image parameters for model '{tool.id}'")

    single_image = input_urls[0] if input_urls else None
    multi_images = input_urls if input_urls and tool.max_input_images > 1 else None
    unified_params = UnifiedImageParameters(
        prompt = prompt,
        aspect_ratio = resolve_aspect_ratio(tool, aspect_ratio, input_urls),
        size = output_size or "2K",
        image = single_image,
        input_image = single_image,
        image_input = multi_images,
        input_images = multi_images,
    )

    if tool == IMAGE_GEN_EDIT_FLUX_2_PRO:
        return replace(unified_params, resolution = convert_size_to_mp(unified_params.size), safety_tolerance = 5)
    elif tool == IMAGE_GEN_EDIT_FLUX_2_MAX:
        return replace(unified_params, resolution = convert_size_to_mp(unified_params.size), safety_tolerance = 5)
    elif tool == IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO:
        return unified_params
    elif tool == IMAGE_GEN_EDIT_GPT_IMAGE_1_5:
        return unified_params
    elif tool == IMAGE_GEN_EDIT_GPT_IMAGE_2:
        return unified_params
    elif tool == IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA:
        return unified_params
    elif tool == IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO:
        return replace(unified_params, resolution = convert_size_to_k(unified_params.size))
    elif tool == IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_2:
        return replace(unified_params, resolution = convert_size_to_k(unified_params.size))
    elif tool == IMAGE_GEN_EDIT_SEEDREAM_4:
        return replace(unified_params, size = convert_size_to_k(unified_params.size))
    elif tool == IMAGE_GEN_EDIT_SEEDREAM_4_5:
        normalized_size = convert_size_to_k(unified_params.size)
        clamped_size = "2K" if normalized_size == "1K" else normalized_size
        return replace(unified_params, size = clamped_size)
    elif tool == NANO_BANANA:
        ar = unified_params.aspect_ratio if unified_params.aspect_ratio != "match_input_image" else None
        return replace(unified_params, size = convert_size_to_k(unified_params.size), aspect_ratio = ar)
    elif tool == NANO_BANANA_PRO:
        ar = unified_params.aspect_ratio if unified_params.aspect_ratio != "match_input_image" else None
        return replace(unified_params, size = convert_size_to_k(unified_params.size), aspect_ratio = ar)
    elif tool == NANO_BANANA_2:
        ar = unified_params.aspect_ratio if unified_params.aspect_ratio != "match_input_image" else None
        return replace(unified_params, size = convert_size_to_k(unified_params.size), aspect_ratio = ar)
    elif tool == IMAGE_GEN_GROK_IMAGINE:
        ar = unified_params.aspect_ratio if unified_params.aspect_ratio != "match_input_image" else None
        return replace(unified_params, resolution = convert_size_to_k(unified_params.size).lower(), aspect_ratio = ar)
    elif tool == IMAGE_GEN_GROK_IMAGINE_QUALITY:
        ar = unified_params.aspect_ratio if unified_params.aspect_ratio != "match_input_image" else None
        return replace(unified_params, resolution = convert_size_to_k(unified_params.size).lower(), aspect_ratio = ar)
    else:
        log.w(f"Unknown model '{tool.id}', using default mapping")
        return unified_params


def filter_replicate_params(tool: ExternalTool, parameters: UnifiedImageParameters) -> dict:
    allowed = ALLOWED_REPLICATE_PARAMS.get(tool.id)
    return {
        key: value
        for key, value in asdict(parameters).items()
        if value is not None and (allowed is None or key in allowed)
    }


def resolve_aspect_ratio(
    tool: ExternalTool,
    aspect_ratio: str | None,
    input_urls: list[str] | None = None,
) -> str:
    is_editing = bool(input_urls)
    log.t(f"Resolving aspect ratio for '{tool.id}'... is_editing: {is_editing}, requested: '{aspect_ratio}'")

    # no aspect ratio requested
    if not aspect_ratio:
        log.t("No aspect ratio requested, using default: 'match_input_image' with input references, '2:3' otherwise")
        return "match_input_image" if is_editing else "2:3"
    cleaned = "".join(aspect_ratio.split())

    # check if match_input_image is requested
    if cleaned == "match_input_image":
        if not is_editing:
            log.w(f"'match_input_image' not supported for '{tool.id}' without input references, using '2:3'")
            return "2:3"
        log.t("Using 'match_input_image' for editing, as requested")
        return cleaned

    return resolve_closest_aspect_ratio(
        aspect_ratio = cleaned,
        supported_aspect_ratios = VALID_ASPECT_RATIOS,
        default_aspect_ratio = "match_input_image" if is_editing else "2:3",
    )
