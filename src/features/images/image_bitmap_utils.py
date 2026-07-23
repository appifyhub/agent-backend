import colorsys
import io
import math
import random
import tempfile
from pathlib import Path

from PIL import Image

from features.chat.supported_files import detect_image_format
from features.images.image_color_utils import relative_luminance

INDIGO = (34, 43, 78)
BURGUNDY = (63, 19, 49)
CORAL = (255, 108, 123)
AMBER = (249, 168, 146)
MESH_PALETTE = [INDIGO, BURGUNDY, CORAL, AMBER]
DARK_MESH_COLOR_SCALE = 0.50
COOL_MESH_COLORS = {INDIGO, BURGUNDY}
COOL_MESH_COLOR_OVERRIDES = {
    INDIGO: (42, 69, 176),
    BURGUNDY: (117, 75, 166),
}

ANALYSIS_MAX_DIMENSION = 64
MESH_MAX_DIMENSION = 512
FIELD_CENTERS = [
    (0.22, 0.22),
    (0.78, 0.22),
    (0.22, 0.78),
    (0.78, 0.78),
]
FIELD_JITTER = 0.035
LIGHT_FIELD_OPACITY = 56
DARK_FIELD_OPACITY = 112
LIGHT_FIELD_SPREAD = (0.34, 0.23)
DARK_FIELD_SPREAD = (0.42, 0.30)


def image_has_transparency(input_path: str) -> bool:
    with Image.open(input_path) as image:
        return _image_has_transparency(image)


def visible_content_is_light(image: Image.Image) -> bool:
    sample = image.convert("RGBA")
    sample.thumbnail(
        (ANALYSIS_MAX_DIMENSION, ANALYSIS_MAX_DIMENSION),
        Image.Resampling.LANCZOS,
    )

    weighted_luminance = 0.0
    visible_weight = 0.0
    for red, green, blue, alpha in sample.get_flattened_data():
        if alpha == 0:
            continue
        weight = alpha / 255
        weighted_luminance += relative_luminance((red, green, blue)) * weight
        visible_weight += weight

    if visible_weight == 0:
        return False
    return weighted_luminance / visible_weight > 0.5


def add_outgoing_png_background(input_path: str) -> str:
    with Path(input_path).open("rb") as file:
        if detect_image_format(file.read(32)) != "png":
            return input_path

    with Image.open(input_path) as image:
        if image.format != "PNG" or not _image_has_transparency(image):
            return input_path

        source = image.convert("RGBA")
        is_light = visible_content_is_light(source)
        shade_rgb = dominant_visible_color(source)
        background = _render_mesh_background(source.size, is_light, shade_rgb)
        background.alpha_composite(source)

        output = io.BytesIO()
        background.convert("RGB").save(output, format = "PNG", optimize = True)
        return _write_temp_file(output.getvalue())


def _render_mesh_background(size: tuple[int, int], is_light: bool, shade_rgb: tuple[int, int, int] | None = None) -> Image.Image:
    work_size = _bounded_size(size)
    base_color = (255, 255, 255, 255) if is_light else (0, 0, 0, 255)
    spread = LIGHT_FIELD_SPREAD if is_light else DARK_FIELD_SPREAD

    background = Image.new("RGBA", work_size, base_color)
    colors = _mesh_palette(shade_rgb, is_light) if shade_rgb else _base_mesh_palette(is_light)
    random.shuffle(colors)

    for (center_x, center_y), color in zip(FIELD_CENTERS, colors, strict = True):
        jittered_x = center_x + random.uniform(-FIELD_JITTER, FIELD_JITTER)
        jittered_y = center_y + random.uniform(-FIELD_JITTER, FIELD_JITTER)
        pixel_x = round(work_size[0] * jittered_x)
        pixel_y = round(work_size[1] * jittered_y)
        angle = random.uniform(0, math.pi)
        field_opacity = _field_opacity(color, is_light)
        mask = _radial_field_mask(
            work_size,
            (pixel_x, pixel_y),
            spread,
            field_opacity,
            angle,
        )

        field_color = COOL_MESH_COLOR_OVERRIDES.get(color, color)
        field = Image.new("RGBA", work_size, (*field_color, 255))
        field.putalpha(mask)
        background.alpha_composite(field)

    if work_size != size:
        return background.resize(size, Image.Resampling.LANCZOS)
    return background


def dominant_visible_color(image: Image.Image) -> tuple[int, int, int] | None:
    sample = image.convert("RGBA")
    sample.thumbnail((ANALYSIS_MAX_DIMENSION, ANALYSIS_MAX_DIMENSION), Image.Resampling.LANCZOS)

    hue_x = 0.0
    hue_y = 0.0
    saturation_total = 0.0
    value_total = 0.0
    total_weight = 0.0
    for red, green, blue, alpha in sample.get_flattened_data():
        if alpha == 0:
            continue
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if saturation < 0.12:
            continue
        weight = (alpha / 255) * saturation * saturation
        angle = hue * math.tau
        hue_x += math.cos(angle) * weight
        hue_y += math.sin(angle) * weight
        saturation_total += saturation * weight
        value_total += value * weight
        total_weight += weight

    if total_weight == 0:
        return None
    hue = (math.atan2(hue_y, hue_x) / math.tau) % 1.0
    saturation = min(1.0, saturation_total / total_weight * 1.15)
    value = value_total / total_weight
    return hsv_to_rgb(hue, saturation, value)


def _mesh_palette(shade_rgb: tuple[int, int, int], is_light: bool) -> list[tuple[int, int, int]]:
    hue, saturation, value = colorsys.rgb_to_hsv(
        shade_rgb[0] / 255,
        shade_rgb[1] / 255,
        shade_rgb[2] / 255,
    )
    luminance = relative_luminance(shade_rgb)
    base_palette = _base_mesh_palette(is_light)
    if saturation < 0.18 and (luminance < 0.16 or luminance > 0.84 or value < 0.20 or value > 0.92):
        return base_palette

    target_saturation = max(saturation, 0.50 if is_light else 0.65)
    target_value = 0.78 if is_light else 0.96
    shifts = (-0.07, 0.07, 0.18, 0.50)
    hue_palette = [
        hsv_to_rgb((hue + shift) % 1.0, min(1.0, target_saturation), target_value)
        for shift in shifts
    ]
    shift_weight = min(0.70, max(0.0, (saturation - 0.18) / 0.45))
    return [
        blend_rgb(base_color, hue_color, shift_weight)
        for base_color, hue_color in zip(base_palette, hue_palette, strict = True)
    ]


def scale_rgb(color: tuple[int, int, int], scale: float) -> tuple[int, int, int]:
    return (
        round(color[0] * scale),
        round(color[1] * scale),
        round(color[2] * scale),
    )


def hsv_to_rgb(hue: float, saturation: float, value: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return round(red * 255), round(green * 255), round(blue * 255)


def blend_rgb(
    base_color: tuple[int, int, int],
    target_color: tuple[int, int, int],
    weight: float,
) -> tuple[int, int, int]:
    return (
        round(base_color[0] + (target_color[0] - base_color[0]) * weight),
        round(base_color[1] + (target_color[1] - base_color[1]) * weight),
        round(base_color[2] + (target_color[2] - base_color[2]) * weight),
    )


def _base_mesh_palette(is_light: bool) -> list[tuple[int, int, int]]:
    if is_light:
        return MESH_PALETTE.copy()
    return [scale_rgb(color, DARK_MESH_COLOR_SCALE) for color in MESH_PALETTE]


def _is_cool_mesh_color(color: tuple[int, int, int]) -> bool:
    if color in COOL_MESH_COLORS:
        return True
    hue, saturation, _ = colorsys.rgb_to_hsv(color[0] / 255, color[1] / 255, color[2] / 255)
    return saturation > 0.25 and 0.55 <= hue <= 0.90


def _field_opacity(color: tuple[int, int, int], is_light: bool) -> int:
    if is_light:
        multiplier = 1.30 if _is_cool_mesh_color(color) else 1.0
        return round(LIGHT_FIELD_OPACITY * multiplier)

    multiplier = 1.25 if _is_cool_mesh_color(color) else 0.85
    return round(DARK_FIELD_OPACITY * multiplier)


def _radial_field_mask(
    size: tuple[int, int],
    center: tuple[int, int],
    spread: tuple[float, float],
    opacity: int,
    angle: float,
) -> Image.Image:
    width, height = size
    center_x, center_y = center
    angle_cos = math.cos(angle)
    angle_sin = math.sin(angle)
    pixels = []

    for pixel_y in range(height):
        offset_y = (pixel_y - center_y) / height
        for pixel_x in range(width):
            offset_x = (pixel_x - center_x) / width
            along = angle_cos * offset_x + angle_sin * offset_y
            across = -angle_sin * offset_x + angle_cos * offset_y
            falloff = math.exp(-((along / spread[0]) ** 2 + (across / spread[1]) ** 2))
            pixels.append(round(opacity * falloff))

    mask = Image.new("L", size)
    mask.putdata(pixels)
    return mask


def _bounded_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    scale = min(1.0, MESH_MAX_DIMENSION / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _image_has_transparency(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return image.getchannel("A").getextrema()[0] < 255
    if image.info.get("transparency") is not None:
        return image.convert("RGBA").getchannel("A").getextrema()[0] < 255
    return False


def _write_temp_file(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete = False, suffix = ".png") as tmp:
        tmp.write(content)
        tmp.flush()
        return tmp.name
