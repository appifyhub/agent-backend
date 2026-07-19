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
COOL_MESH_COLORS = {INDIGO, BURGUNDY}
COOL_MESH_COLOR_OVERRIDES = {
    INDIGO: (42, 69, 176),
    BURGUNDY: (117, 75, 166),
}

ANALYSIS_MAX_DIMENSION = 64
MESH_MAX_DIMENSION = 512
FIELD_CENTERS = [
    (0.30, 0.30),
    (0.70, 0.30),
    (0.30, 0.70),
    (0.70, 0.70),
]
FIELD_JITTER = 0.04
LIGHT_FIELD_OPACITY = 36
DARK_FIELD_OPACITY = 80
LIGHT_FIELD_SPREAD = (0.27, 0.18)
DARK_FIELD_SPREAD = (0.34, 0.23)


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
        background = _render_mesh_background(source.size, is_light)
        background.alpha_composite(source)

        output = io.BytesIO()
        background.convert("RGB").save(output, format = "PNG", optimize = True)
        return _write_temp_file(output.getvalue())


def _render_mesh_background(size: tuple[int, int], is_light: bool) -> Image.Image:
    work_size = _bounded_size(size)
    base_color = (255, 255, 255, 255) if is_light else (0, 0, 0, 255)
    spread = LIGHT_FIELD_SPREAD if is_light else DARK_FIELD_SPREAD

    background = Image.new("RGBA", work_size, base_color)
    colors = MESH_PALETTE.copy()
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


def _field_opacity(color: tuple[int, int, int], is_light: bool) -> int:
    if is_light:
        multiplier = 1.30 if color in COOL_MESH_COLORS else 1.0
        return round(LIGHT_FIELD_OPACITY * multiplier)

    multiplier = 1.20 if color in COOL_MESH_COLORS else 0.70
    return round(DARK_FIELD_OPACITY * multiplier * 0.90)


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
