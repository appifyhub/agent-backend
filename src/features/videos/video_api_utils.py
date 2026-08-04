from dataclasses import asdict, dataclass, replace

from features.external_tools.external_tool import ExternalTool
from features.external_tools.external_tool_library import (
    VIDEO_GEN_P_VIDEO,
    VIDEO_GEN_RAY_3_2,
    VIDEO_GEN_SEEDANCE_2_0,
    VIDEO_GEN_SEEDANCE_2_0_FAST,
    VIDEO_GEN_VEO_3_1,
    VIDEO_GEN_VEO_3_1_FAST,
)
from features.images.image_size_utils import convert_size_to_k, resolve_closest_aspect_ratio
from util import log

DEFAULT_ASPECT_RATIO = "16:9"

P_VIDEO_ASPECT_RATIOS = ["9:16", "2:3", "3:4", "1:1", "4:3", "3:2", "16:9"]
SEEDANCE_ASPECT_RATIOS = ["9:16", "3:4", "1:1", "4:3", "16:9", "21:9"]
VEO_ASPECT_RATIOS = ["9:16", "16:9"]
RAY_ASPECT_RATIOS = ["9:16", "3:4", "1:1", "4:3", "16:9", "21:9"]
VALID_ASPECT_RATIOS = list(dict.fromkeys(P_VIDEO_ASPECT_RATIOS + SEEDANCE_ASPECT_RATIOS + VEO_ASPECT_RATIOS + RAY_ASPECT_RATIOS))

VALID_DURATIONS = {"short", "medium", "long"}

ALLOWED_REPLICATE_PARAMS: dict[str, set[str]] = {
    VIDEO_GEN_P_VIDEO.id: {
        "prompt", "image", "duration", "aspect_ratio", "resolution",
        "fps", "draft", "prompt_upsampling", "disable_safety_filter", "save_audio",
    },
    VIDEO_GEN_SEEDANCE_2_0.id: {
        "prompt", "image", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
    },
    VIDEO_GEN_SEEDANCE_2_0_FAST.id: {
        "prompt", "image", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
    },
    VIDEO_GEN_VEO_3_1.id: {
        "prompt", "image", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
    },
    VIDEO_GEN_VEO_3_1_FAST.id: {
        "prompt", "image", "duration", "aspect_ratio", "resolution", "generate_audio",
    },
    VIDEO_GEN_RAY_3_2.id: {
        "prompt", "start_image", "duration", "aspect_ratio", "resolution", "hdr", "exr_export", "loop",
    },
}


@dataclass(frozen = True)
class UnifiedVideoParameters:
    prompt: str
    duration: int = 5
    aspect_ratio: str | None = None
    size: str = "1K"
    resolution: str = "720p"
    image: str | None = None
    start_image: str | None = None
    reference_images: list[str] | None = None
    fps: int | None = None
    draft: bool | None = None
    prompt_upsampling: bool | None = None
    disable_safety_filter: bool | None = None
    save_audio: bool | None = None
    generate_audio: bool | None = None
    hdr: bool | None = None
    exr_export: bool | None = None
    loop: bool | None = None


def map_to_model_parameters(
    tool: ExternalTool,
    prompt: str = "",
    duration: str | None = None,
    aspect_ratio: str | None = None,
    output_size: str | None = None,
    reference_image_urls: list[str] | None = None,
) -> UnifiedVideoParameters:
    log.d(f"Mapping video parameters for model '{tool.id}'")

    references = reference_image_urls or []
    single_image = references[0] if references and (len(references) == 1 or tool.max_input_images == 1) else None
    multi_images = references[:tool.max_input_images] if len(references) > 1 and tool.max_input_images > 1 else None
    normalized_size = convert_size_to_k(output_size or "1K", fallback = "1K")
    unified_params = UnifiedVideoParameters(
        prompt = prompt,
        duration = resolve_duration(
            tool = tool,
            duration = duration,
            has_input_image = single_image is not None,
            has_reference_images = multi_images is not None,
        ),
        aspect_ratio = resolve_aspect_ratio(tool, aspect_ratio, references),
        size = normalized_size,
        resolution = {"1K": "720p", "2K": "1080p", "4K": "4k"}[normalized_size],
        image = single_image,
        reference_images = multi_images,
    )

    if tool == VIDEO_GEN_P_VIDEO:
        size = "2K" if normalized_size == "4K" else normalized_size
        resolution = "1080p" if size == "2K" else "720p"
        return replace(
            unified_params,
            size = size,
            resolution = resolution,
            fps = 24,
            draft = False,
            prompt_upsampling = False,
            disable_safety_filter = True,
            save_audio = True,
        )
    elif tool == VIDEO_GEN_SEEDANCE_2_0:
        return replace(unified_params, generate_audio = True)
    elif tool == VIDEO_GEN_SEEDANCE_2_0_FAST:
        return replace(unified_params, size = "1K", resolution = "720p", generate_audio = True)
    elif tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
        size = "2K" if normalized_size == "4K" else normalized_size
        resolution = "1080p" if size == "2K" else "720p"
        return replace(unified_params, size = size, resolution = resolution, generate_audio = True)
    elif tool == VIDEO_GEN_RAY_3_2:
        size = "2K" if normalized_size == "4K" else normalized_size
        resolution = "1080p" if size == "2K" else "720p"
        return replace(
            unified_params,
            size = size,
            resolution = resolution,
            image = None,
            start_image = single_image,
            hdr = False,
            exr_export = False,
            loop = False,
        )
    log.w(f"Unknown video model '{tool.id}', using default mapping")
    return unified_params


def filter_replicate_params(tool: ExternalTool, parameters: UnifiedVideoParameters) -> dict:
    allowed = ALLOWED_REPLICATE_PARAMS.get(tool.id)
    return {
        key: value
        for key, value in asdict(parameters).items()
        if value is not None and (allowed is None or key in allowed)
    }


def resolve_duration(
    tool: ExternalTool,
    duration: str | None,
    has_input_image: bool = False,
    has_reference_images: bool = False,
) -> int:
    semantic_duration = (duration or "medium").lower()
    if semantic_duration not in VALID_DURATIONS:
        semantic_duration = "medium"

    if tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
        return {"short": 4, "medium": 5, "long": 10}[semantic_duration]
    elif tool == VIDEO_GEN_VEO_3_1 and has_reference_images:
        return 8
    elif tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
        return {"short": 4, "medium": 6, "long": 8}[semantic_duration]
    elif tool == VIDEO_GEN_RAY_3_2:
        if has_input_image or has_reference_images:
            return 5
        return {"short": 5, "medium": 5, "long": 10}[semantic_duration]

    log.w(f"Unknown video model '{tool.id}', using 5-second duration")
    return 5


def resolve_aspect_ratio(
    tool: ExternalTool,
    aspect_ratio: str | None,
    reference_image_urls: list[str] | None = None,
) -> str | None:
    references = reference_image_urls or []
    has_single_user_image = bool(references) and (len(references) == 1 or tool.max_input_images == 1)
    has_user_images = len(references) > 1 and tool.max_input_images > 1

    if has_single_user_image and tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_RAY_3_2):
        return None
    if has_user_images and tool == VIDEO_GEN_VEO_3_1:
        return "16:9"

    if not aspect_ratio:
        if not references:
            return DEFAULT_ASPECT_RATIO
        if tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            return "adaptive"
        return None

    cleaned = "".join(aspect_ratio.split())
    if cleaned == "match_input_image":
        if not references:
            log.w(f"'match_input_image' not supported for '{tool.id}' without reference images, using '{DEFAULT_ASPECT_RATIO}'")
            return DEFAULT_ASPECT_RATIO
        if tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            return "adaptive"
        return None

    if tool == VIDEO_GEN_P_VIDEO:
        supported_aspect_ratios = P_VIDEO_ASPECT_RATIOS
    elif tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
        supported_aspect_ratios = SEEDANCE_ASPECT_RATIOS
    elif tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
        supported_aspect_ratios = VEO_ASPECT_RATIOS
    elif tool == VIDEO_GEN_RAY_3_2:
        supported_aspect_ratios = RAY_ASPECT_RATIOS
    else:
        supported_aspect_ratios = VALID_ASPECT_RATIOS

    return resolve_closest_aspect_ratio(
        aspect_ratio = cleaned,
        supported_aspect_ratios = supported_aspect_ratios,
        default_aspect_ratio = DEFAULT_ASPECT_RATIO,
    )
