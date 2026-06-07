import base64
import io
import re
from pathlib import Path

from PIL import Image, ImageFont

from util.config import config

FONT_PATH = Path(config.fonts_dir) / "GoogleSans-Variable.ttf"
FONT_NAME = "Google Sans"
EMOJI_FONT_NAME = "Noto Color Emoji"

EMOJI_RE = re.compile(
    "(?:"
    "[\U0001F1E6-\U0001F1FF]"
    "|[\U0001F300-\U0001F5FF]"
    "|[\U0001F600-\U0001F64F]"
    "|[\U0001F680-\U0001F6FF]"
    "|[\U0001F700-\U0001F77F]"
    "|[\U0001F780-\U0001F7FF]"
    "|[\U0001F800-\U0001F8FF]"
    "|[\U0001F900-\U0001F9FF]"
    "|[\U0001FA00-\U0001FAFF]"
    "|[☀-➿]"
    "|[⌀-⏿]"
    "|[⬀-⯿]"
    ")"
    "[️‍\U0001F3FB-\U0001F3FF]*"
    "(?:"
    "(?:"
    "[\U0001F1E6-\U0001F1FF]"
    "|[\U0001F300-\U0001F5FF]"
    "|[\U0001F600-\U0001F64F]"
    "|[\U0001F680-\U0001F6FF]"
    "|[\U0001F700-\U0001F77F]"
    "|[\U0001F780-\U0001F7FF]"
    "|[\U0001F800-\U0001F8FF]"
    "|[\U0001F900-\U0001F9FF]"
    "|[\U0001FA00-\U0001FAFF]"
    "|[☀-➿]"
    "|[⌀-⏿]"
    "|[⬀-⯿]"
    ")"
    "[️‍\U0001F3FB-\U0001F3FF]*"
    ")*",
)


def pillow_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def text_width(text: str, size: int) -> int:
    font = pillow_font(size)
    return round(font.getlength(text))


def emoji_pillow_font(size: int) -> ImageFont.FreeTypeFont | None:
    for p in Path(config.fonts_dir).glob("*.ttf"):
        if "emoji" in p.name.lower() or "colr" in p.name.lower():
            return ImageFont.truetype(str(p), size)
    return None


def emoji_text_width(text: str, size: int) -> int:
    emoji_font = emoji_pillow_font(size)
    if emoji_font is None:
        return text_width(text, size)
    return round(emoji_font.getlength(text))


def emoji_split(text: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    pos = 0
    for match in EMOJI_RE.finditer(text):
        s, e = match.span()
        if s > pos:
            out.append((text[pos:s], False))
        out.append((text[s:e], True))
        pos = e
    if pos < len(text):
        out.append((text[pos:], False))
    return out or [(text, False)]


def segment_width(text: str, font_size: int, is_emoji: bool) -> int:
    if is_emoji:
        return emoji_text_width(text, font_size)
    return text_width(text, font_size)


def render_text_segments(
    segments: list[tuple[str, str, str, bool]],
    x: int,
    y: int,
    font_size: int,
    fill_default: str,
    weight: int = 400,
) -> tuple[list[str], int]:
    out = []
    cur_x = x
    for text, fill, decoration, is_emoji in segments:
        family = EMOJI_FONT_NAME if is_emoji else FONT_NAME
        applied_fill = fill or fill_default
        bold_attrs = ""
        if weight == 700 and not is_emoji:
            bold_attrs = f' stroke="{applied_fill}" stroke-width="0.7" paint-order="stroke"'
        out.append(
            f'<text x="{cur_x}" y="{y}" font-family="{family}" font-size="{font_size}" '
            f'fill="{applied_fill}"{decoration}{bold_attrs} xml:space="preserve">{escape_xml(text)}</text>',
        )
        cur_x += segment_width(text, font_size, is_emoji)
    return out, cur_x


def b64_image(data: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def image_mime(data: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "JPEG").upper()
        return {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "GIF": "image/gif",
            "WEBP": "image/webp",
            "ICO": "image/x-icon",
        }.get(fmt, "image/jpeg")
    except Exception:
        return "image/jpeg"


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def rounded_rect_path(x: int, y: int, w: int, h: int, tl: int, tr: int, br: int, bl: int) -> str:
    return (
        f"M {x + tl},{y} "
        f"H {x + w - tr} "
        f"Q {x + w},{y} {x + w},{y + tr} "
        f"V {y + h - br} "
        f"Q {x + w},{y + h} {x + w - br},{y + h} "
        f"H {x + bl} "
        f"Q {x},{y + h} {x},{y + h - bl} "
        f"V {y + tl} "
        f"Q {x},{y} {x + tl},{y} Z"
    )


def word_wrap_truncate(text: str, max_width: int, font_size: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    words = text.split()
    current = ""
    remaining = False
    for i, word in enumerate(words):
        candidate = (current + " " + word).strip()
        if text_width(candidate, font_size) <= max_width:
            current = candidate
        else:
            if current:
                if len(lines) >= max_lines - 1:
                    remaining = True
                    lines.append(trim_trailing_sep(current) + "…")
                    return lines
                lines.append(current)
            if text_width(word, font_size) > max_width:
                truncated = word
                while truncated and text_width(truncated + "…", font_size) > max_width:
                    truncated = truncated[:-1]
                current = truncated + "…" if truncated else word[:1] + "…"
                remaining = True
            else:
                current = word
        if i < len(words) - 1 and len(lines) >= max_lines:
            remaining = True
            break
    if current and not remaining:
        if len(lines) >= max_lines:
            lines[-1] = trim_trailing_sep(lines[-1]) + "…"
        else:
            lines.append(current)
    elif current and remaining:
        if len(lines) < max_lines:
            lines.append(trim_trailing_sep(current) + "…")
    return lines[:max_lines] or [""]


def trim_trailing_sep(text: str) -> str:
    return text.rstrip(" -–—:|/")
