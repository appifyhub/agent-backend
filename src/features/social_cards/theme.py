import colorsys
import io
from dataclasses import dataclass

from PIL import Image

from features.images.image_color_utils import relative_luminance
from features.social_cards.brand import BRAND_GRADIENT_END, BRAND_GRADIENT_START
from util import log


@dataclass(frozen = True)
class ThemeColors:
    gradient_start: str  # hex #RRGGBB
    gradient_end: str  # hex #RRGGBB
    text_color: str  # "#000000" or "#ffffff"


def pick_theme(
    profile_bytes: bytes | None,
    media_bytes_list: list[bytes],
) -> ThemeColors:
    primary = _dominant_from_combined(media_bytes_list) if media_bytes_list else None
    if primary is None:
        primary = _dominant_from_bytes(profile_bytes)
    if primary is None:
        return ThemeColors(
            gradient_start = BRAND_GRADIENT_START,
            gradient_end = BRAND_GRADIENT_END,
            text_color = "#ffffff",
        )
    primary = _darken_unless_white(primary)
    secondary = _derive_gradient_end(primary)
    text_color = _contrast_text(primary)
    light, dark = (primary, secondary) if sum(primary) >= sum(secondary) else (secondary, primary)
    return ThemeColors(
        gradient_start = _rgb_to_hex(light),
        gradient_end = _rgb_to_hex(dark),
        text_color = text_color,
    )


def _dominant_from_bytes(data: bytes | None) -> tuple[int, int, int] | None:
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize((64, 64))
        quantized = img.quantize(colors = 8)
        palette = quantized.getpalette()
        if not palette:
            return None
        best_rgb = _most_saturated_from_palette(palette, 8)
        return best_rgb
    except Exception as e:
        log.w("Dominant color extraction failed", e)
        return None


def _dominant_from_combined(images: list[bytes]) -> tuple[int, int, int] | None:
    try:
        strips = []
        for data in images:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB").resize((32, 32))
                strips.append(img)
            except Exception:
                continue
        if not strips:
            return None
        combined_w = 32 * len(strips)
        canvas = Image.new("RGB", (combined_w, 32))
        for i, strip in enumerate(strips):
            canvas.paste(strip, (i * 32, 0))
        quantized = canvas.quantize(colors = 8)
        palette = quantized.getpalette()
        if not palette:
            return None
        return _most_saturated_from_palette(palette, 8)
    except Exception as e:
        log.w("Combined dominant color extraction failed", e)
        return None


def _most_saturated_from_palette(palette: list[int], count: int) -> tuple[int, int, int]:
    best_rgb = (128, 128, 128)
    best_sat = -1.0
    actual_count = min(count, len(palette) // 3)
    for i in range(actual_count):
        r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
        _, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > best_sat:
            best_sat = s
            best_rgb = (r, g, b)
    return best_rgb


def _darken_unless_white(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    if r == 255 and g == 255 and b == 255:
        return rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    new_v = max(0.0, v - 0.10)
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, new_v)
    return (round(nr * 255), round(ng * 255), round(nb * 255))


def _derive_gradient_end(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    lightness = (r + g + b) / (3 * 255)
    v_shift = 0.2 if lightness >= 0.5 else -0.2
    new_v = max(0.0, min(1.0, v + v_shift))
    # hue shift: toward red (0°) if closer to blue side, toward blue if closer to red
    hue_shift = 10 / 360
    new_h = (h + hue_shift) % 1.0
    nr, ng, nb = colorsys.hsv_to_rgb(new_h, s, new_v)
    return (round(nr * 255), round(ng * 255), round(nb * 255))


def _contrast_text(rgb: tuple[int, int, int]) -> str:
    return "#000000" if relative_luminance(rgb) > 0.5 else "#ffffff"


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
