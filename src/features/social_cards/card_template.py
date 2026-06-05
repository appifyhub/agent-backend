import base64
import io
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageFont

from features.social_cards.card_layout import (
    AVATAR_GAP,
    AVATAR_SIZE,
    CARD_CORNER_RADIUS,
    CARD_INNER_PAD,
    CARD_OUTER_PAD,
    CARD_SECTION_GAP,
    DIVIDER_OPACITY,
    DROP_SHADOW_BLUR,
    DROP_SHADOW_DY,
    DROP_SHADOW_OPACITY,
    FONT_SIZE_BODY,
    FONT_SIZE_DATE,
    FONT_SIZE_FOOTER,
    FONT_SIZE_NAME,
    FOOTER_OPACITY,
    LINE_HEIGHT_BODY,
    LOGO_CIRCLE_R,
    LOGO_SIZE,
    PHOTO_CORNER_RADIUS,
    PHOTO_GAP,
    X_ICON_SIZE,
)
from features.social_cards.theme import ThemeColors
from features.web_browsing.twitter_status_fetcher import TweetData
from util.config import config

_FONT_PATH = Path(config.fonts_dir) / "Heebo-Variable.ttf"
_FONT_NAME = "Heebo"
_EMOJI_FONT_NAME = "Noto Color Emoji"

_FONT_B64: str | None = None
_LOGO_CACHE: dict[str, bytes] = {}

_SPECIAL_TOKEN_RE = re.compile(r"(https?://\S+|www\.\S+|@\w+|#\w+|\$[A-Za-z]+)")

_EMOJI_RE = re.compile(
    "(?:"
    "[\U0001F1E6-\U0001F1FF]"      # regional indicators (flags)
    "|[\U0001F300-\U0001F5FF]"      # misc symbols & pictographs
    "|[\U0001F600-\U0001F64F]"      # emoticons
    "|[\U0001F680-\U0001F6FF]"      # transport & map
    "|[\U0001F700-\U0001F77F]"      # alchemical
    "|[\U0001F780-\U0001F7FF]"      # geometric extended
    "|[\U0001F800-\U0001F8FF]"      # supplemental arrows-C
    "|[\U0001F900-\U0001F9FF]"      # supplemental symbols & pictographs
    "|[\U0001FA00-\U0001FAFF]"      # symbols & pictographs ext-A
    "|[☀-➿]"              # misc symbols & dingbats
    "|[⌀-⏿]"              # misc technical
    "|[⬀-⯿]"              # misc symbols & arrows
    ")"
    "[️‍\U0001F3FB-\U0001F3FF]*"  # variation selector, ZWJ, skin tones
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


def _font_b64() -> str:
    global _FONT_B64
    if _FONT_B64 is None:
        _FONT_B64 = base64.b64encode(_FONT_PATH.read_bytes()).decode("ascii")
    return _FONT_B64


def _b64_image(data: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _fetch_logo(key: str) -> bytes:
    if key not in _LOGO_CACHE:
        url = config.logos[key]
        with urllib.request.urlopen(url) as response:
            _LOGO_CACHE[key] = response.read()
    return _LOGO_CACHE[key]


def _logo_svg_b64(key: str) -> str:
    return f"data:image/svg+xml;base64,{base64.b64encode(_fetch_logo(key)).decode('ascii')}"


def _agent_logo_key(theme: ThemeColors) -> str:
    hex_color = theme.gradient_start.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if luminance < 0.3:
        return "agent_logo_light"
    if luminance > 0.7:
        return "agent_logo_dark"
    return "agent_logo_color"


def _x_logo_key(theme: ThemeColors) -> str:
    return "x_logo_light" if theme.text_color == "#ffffff" else "x_logo_dark"


def _accent_color(theme: ThemeColors) -> str:
    h = theme.gradient_start.lstrip("#")
    r, g, b = 255 - int(h[0:2], 16), 255 - int(h[2:4], 16), 255 - int(h[4:6], 16)
    return f"#{r:02x}{g:02x}{b:02x}"


def _image_mime(data: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "JPEG").upper()
        return {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}.get(fmt, "image/jpeg")
    except Exception:
        return "image/jpeg"


def _photo_natural_height(data: bytes, display_w: int) -> int:
    try:
        img = Image.open(io.BytesIO(data))
        if img.width == 0:
            return display_w
        return round(display_w * img.height / img.width)
    except Exception:
        return display_w


def _photo_sort_key(data: bytes) -> int:
    try:
        img = Image.open(io.BytesIO(data))
        if img.height > img.width * 1.05:
            return 0  # portrait first
        if img.width > img.height * 1.05:
            return 2  # landscape last
        return 1  # square middle
    except Exception:
        return 1


def _pillow_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_PATH), size)


def _emoji_pillow_font(size: int) -> ImageFont.FreeTypeFont | None:
    for p in Path(config.fonts_dir).glob("*.ttf"):
        if "emoji" in p.name.lower() or "colr" in p.name.lower():
            return ImageFont.truetype(str(p), size)
    return None


def _text_width(text: str, size: int) -> int:
    font = _pillow_font(size)
    return round(font.getlength(text))


def _emoji_text_width(text: str, size: int) -> int:
    emoji_font = _emoji_pillow_font(size)
    if emoji_font is None:
        return _text_width(text, size)
    return round(emoji_font.getlength(text))


def _word_wrap(text: str, max_width: int, font_size: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if _text_width(candidate, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def _emoji_split(text: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    pos = 0
    for match in _EMOJI_RE.finditer(text):
        s, e = match.span()
        if s > pos:
            out.append((text[pos:s], False))
        out.append((text[s:e], True))
        pos = e
    if pos < len(text):
        out.append((text[pos:], False))
    return out or [(text, False)]


def _segment_width(text: str, font_size: int, is_emoji: bool) -> int:
    if is_emoji:
        return _emoji_text_width(text, font_size)
    return _text_width(text, font_size)


def _render_text_segments(
    segments: list[tuple[str, str, str, bool]],
    x: int,
    y: int,
    font_size: int,
    fill_default: str,
    weight: int = 400,
) -> tuple[list[str], int]:
    """Render (text, fill, decoration, is_emoji) tuples as separate <text> elements at computed x.
    Avoids the usvg panic caused by font-family switches inside a single <text> with flag emoji.
    Bold is achieved via stroke since resvg's variable-font wght axis is inert below size 24."""
    out = []
    cur_x = x
    for text, fill, decoration, is_emoji in segments:
        family = _EMOJI_FONT_NAME if is_emoji else _FONT_NAME
        applied_fill = fill or fill_default
        bold_attrs = ""
        if weight == 700 and not is_emoji:
            bold_attrs = f' stroke="{applied_fill}" stroke-width="0.7" paint-order="stroke"'
        out.append(
            f'<text x="{cur_x}" y="{y}" font-family="{family}" font-size="{font_size}" '
            f'fill="{applied_fill}"{decoration}{bold_attrs} xml:space="preserve">{_escape(text)}</text>',
        )
        cur_x += _segment_width(text, font_size, is_emoji)
    return out, cur_x


def _line_to_segments(line: str, normal_fill: str, accent: str) -> list[tuple[str, str, str, bool]]:
    segments: list[tuple[str, str, str, bool]] = []
    parts = _SPECIAL_TOKEN_RE.split(line)
    for i, part in enumerate(parts):
        if not part:
            continue
        is_special = i % 2 == 1
        fill = accent if is_special else normal_fill
        decoration = ' text-decoration="underline"' if is_special else ""
        for sub_text, is_emoji in _emoji_split(part):
            if sub_text:
                segments.append((sub_text, fill, decoration, is_emoji))
    return segments


def _format_datetime(created_at: str | None) -> str:
    if not created_at:
        return ""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        hour = dt.hour % 12 or 12
        am_pm = "AM" if dt.hour < 12 else "PM"
        return f"{dt.year}-{dt.month:02d}-{dt.day:02d} · UTC {hour}:{dt.minute:02d} {am_pm}"
    except Exception:
        return created_at


def _rounded_rect_path(x: int, y: int, w: int, h: int, tl: int, tr: int, br: int, bl: int) -> str:
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


def _photo_cell_parts(
    cell_id: str,
    x: int,
    y: int,
    w: int,
    h: int,
    photo_b64: str,
    tl: int,
    tr: int,
    br: int,
    bl: int,
) -> tuple[str, str]:
    path = _rounded_rect_path(x, y, w, h, tl, tr, br, bl)
    clip = f'<clipPath id="{cell_id}-clip"><path d="{path}"/></clipPath>'
    img = (
        f'<image clip-path="url(#{cell_id}-clip)" x="{x}" y="{y}" width="{w}" height="{h}" '
        f'href="{photo_b64}" preserveAspectRatio="xMidYMid slice"/>'
    )
    return clip, img


def build_svg(
    tweet: TweetData,
    theme: ThemeColors,
    card_width: int,
    profile_bytes: bytes | None,
    media_bytes: list[bytes],
    short_url: str | None,
) -> str:
    cx = CARD_OUTER_PAD  # card left edge
    inner_w = card_width - 2 * CARD_INNER_PAD
    body_x = cx + CARD_INNER_PAD
    r = CARD_CORNER_RADIUS
    accent = _accent_color(theme)

    defs: list[str] = []
    content: list[str] = []

    # Font
    defs.append(
        f'<style type="text/css">'
        f'@font-face {{font-family:"{_FONT_NAME}";font-style:normal;font-weight:100 900;'
        f'src:url("data:font/truetype;base64,{_font_b64()}") format("truetype");}}'
        f"</style>",
    )

    # Background gradient
    defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="0.6" y2="1" gradientUnits="objectBoundingBox">'
        f'<stop offset="0%" stop-color="{theme.gradient_start}"/>'
        f'<stop offset="100%" stop-color="{theme.gradient_end}"/>'
        f"</linearGradient>",
    )

    # Drop shadow filter
    defs.append(
        f'<filter id="shadow" x="-8%" y="-8%" width="116%" height="116%">'
        f'<feDropShadow dx="0" dy="{DROP_SHADOW_DY}" stdDeviation="{DROP_SHADOW_BLUR}" '
        f'flood-color="#000000" flood-opacity="{DROP_SHADOW_OPACITY}"/>'
        f"</filter>",
    )

    # Avatar clip
    av_cx = cx + CARD_INNER_PAD + AVATAR_SIZE // 2
    av_cy_center = CARD_OUTER_PAD + CARD_INNER_PAD + AVATAR_SIZE // 2
    defs.append(f'<clipPath id="avatar-clip"><circle cx="{av_cx}" cy="{av_cy_center}" r="{AVATAR_SIZE // 2}"/></clipPath>')

    # Current Y cursor (inside SVG coords, card top = CARD_OUTER_PAD)
    y = CARD_OUTER_PAD + CARD_INNER_PAD

    # Header
    if profile_bytes:
        avatar_b64 = _b64_image(profile_bytes, _image_mime(profile_bytes))
        content.append(
            f'<image clip-path="url(#avatar-clip)" x="{cx + CARD_INNER_PAD}" y="{y}" '
            f'width="{AVATAR_SIZE}" height="{AVATAR_SIZE}" href="{avatar_b64}" preserveAspectRatio="xMidYMid slice"/>',
        )
    else:
        initial = (tweet.user.handle or "?")[0].upper()
        content.append(
            f'<circle cx="{av_cx}" cy="{av_cy_center}" r="{AVATAR_SIZE // 2}" fill="{theme.text_color}" fill-opacity="0.2"/>'
            f'<text x="{av_cx}" y="{av_cy_center + 8}" text-anchor="middle" font-family="{_FONT_NAME}" '
            f'font-size="{AVATAR_SIZE // 2}" fill="{theme.text_color}">{initial}</text>',
        )

    name_x = cx + CARD_INNER_PAD + AVATAR_SIZE + AVATAR_GAP
    _name_date_span = FONT_SIZE_DATE + 8
    _visual_block_h = FONT_SIZE_NAME + _name_date_span
    name_y = y + (AVATAR_SIZE + _visual_block_h) // 2 - _name_date_span
    date_y = name_y + _name_date_span

    def _name_segments(text: str) -> list[tuple[str, str, str, bool]]:
        return [(sub, theme.text_color, "", is_emoji) for sub, is_emoji in _emoji_split(text) if sub]

    if tweet.user.name:
        name_elems, name_end_x = _render_text_segments(
            _name_segments(tweet.user.name), name_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 700,
        )
        content.extend(name_elems)
        handle_elems, _ = _render_text_segments(
            _name_segments(f" (@{tweet.user.handle})"), name_end_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 400,
        )
        content.extend(handle_elems)
    else:
        handle_elems, _ = _render_text_segments(
            _name_segments(f"@{tweet.user.handle}"), name_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 700,
        )
        content.extend(handle_elems)
    dt_str = _format_datetime(tweet.created_at)
    if dt_str:
        content.append(
            f'<text x="{name_x}" y="{date_y}" font-family="{_FONT_NAME}" font-size="{FONT_SIZE_DATE}" '
            f'fill="{theme.text_color}" fill-opacity="0.7">{dt_str}</text>',
        )

    # Agent logo (top-right) with contrast circle
    logo_cx = cx + card_width - CARD_INNER_PAD - LOGO_CIRCLE_R
    logo_cy = y + AVATAR_SIZE // 2
    logo_key = _agent_logo_key(theme)
    logo_b64 = _logo_svg_b64(logo_key)
    if logo_key == "agent_logo_color":
        content.append(
            f'<circle cx="{logo_cx}" cy="{logo_cy}" r="{LOGO_CIRCLE_R}" '
            f'fill="{theme.text_color}" fill-opacity="0.5"/>',
        )
    else:
        content.append(
            f'<circle cx="{logo_cx}" cy="{logo_cy}" r="{LOGO_CIRCLE_R}" '
            f'fill="none" stroke="{theme.text_color}" stroke-width="1.3"/>',
        )
    logo_x = logo_cx - LOGO_SIZE // 2
    logo_y = logo_cy - LOGO_SIZE // 2 - round(LOGO_SIZE * 0.05)
    logo_opacity = ' opacity="0.8"' if logo_key != "agent_logo_color" else ""
    content.append(
        f'<image x="{logo_x}" y="{logo_y}" width="{LOGO_SIZE}" height="{LOGO_SIZE}" href="{logo_b64}"{logo_opacity}/>',
    )

    y += AVATAR_SIZE + CARD_SECTION_GAP

    # Divider
    content.append(
        f'<line x1="{body_x}" y1="{y}" x2="{body_x + inner_w}" y2="{y}" '
        f'stroke="{theme.text_color}" stroke-opacity="{DIVIDER_OPACITY}" stroke-width="1"/>',
    )
    y += CARD_SECTION_GAP

    # Tweet body with colored tokens
    lines = _word_wrap(tweet.text, inner_w, FONT_SIZE_BODY)
    if lines:
        for i, ln in enumerate(lines):
            line_y = y + FONT_SIZE_BODY + i * LINE_HEIGHT_BODY
            segments = _line_to_segments(ln, theme.text_color, accent)
            if not segments:
                continue
            line_elems, _ = _render_text_segments(segments, body_x, line_y, FONT_SIZE_BODY, theme.text_color)
            content.extend(line_elems)
        y += len(lines) * LINE_HEIGHT_BODY + CARD_SECTION_GAP

    # Photos — sorted portrait → square → landscape
    if media_bytes:
        sorted_media = sorted(media_bytes, key = _photo_sort_key)
        total = len(sorted_media)
        keys = [_photo_sort_key(d) for d in sorted_media]
        n_portrait = keys.count(0)
        cell = 0  # global cell index for unique clip-path IDs

        def _add_cell(photo_data: bytes, cx: int, cy: int, w: int, h: int, tl: int, tr: int, br: int, bl: int) -> None:
            nonlocal cell
            b64 = _b64_image(photo_data, _image_mime(photo_data))
            clip, img = _photo_cell_parts(f"photo-{cell}", cx, cy, w, h, b64, tl, tr, br, bl)
            defs.append(clip)
            content.append(img)
            cell += 1

        R = PHOTO_CORNER_RADIUS

        if total == 2 and all(k <= 1 for k in keys):
            # 2 portrait/square → side by side
            col_w = (inner_w - PHOTO_GAP) // 2
            ph = max(_photo_natural_height(sorted_media[0], col_w), _photo_natural_height(sorted_media[1], col_w))
            _add_cell(sorted_media[0], body_x, y, col_w, ph, R, 2, 2, R)
            _add_cell(sorted_media[1], body_x + col_w + PHOTO_GAP, y, col_w, ph, 2, R, R, 2)
            y += ph

        elif total == 3 and n_portrait == 3:
            # 3 portraits → 3 columns
            col_w = (inner_w - 2 * PHOTO_GAP) // 3
            ph = max(_photo_natural_height(d, col_w) for d in sorted_media)
            for i, d in enumerate(sorted_media):
                x_off = body_x + i * (col_w + PHOTO_GAP)
                tl = R if i == 0 else 2
                bl = R if i == 0 else 2
                tr = R if i == 2 else 2
                br = R if i == 2 else 2
                _add_cell(d, x_off, y, col_w, ph, tl, tr, br, bl)
            y += ph

        elif total == 3 and n_portrait == 2 and keys.count(1) == 1:
            # 2 portraits + 1 square → portraits side by side on top, square full-width below
            portraits = [d for d, k in zip(sorted_media, keys) if k == 0]
            square = next(d for d, k in zip(sorted_media, keys) if k == 1)
            col_w = (inner_w - PHOTO_GAP) // 2
            ph_top = max(_photo_natural_height(portraits[0], col_w), _photo_natural_height(portraits[1], col_w))
            _add_cell(portraits[0], body_x, y, col_w, ph_top, R, 2, 2, 2)
            _add_cell(portraits[1], body_x + col_w + PHOTO_GAP, y, col_w, ph_top, 2, R, 2, 2)
            y += ph_top + PHOTO_GAP
            ph_bot = _photo_natural_height(square, inner_w)
            _add_cell(square, body_x, y, inner_w, ph_bot, 2, 2, R, R)
            y += ph_bot

        elif total == 4 and n_portrait == 4:
            # 4 portraits → 2×2 grid
            col_w = (inner_w - PHOTO_GAP) // 2
            ph_top = max(_photo_natural_height(sorted_media[0], col_w), _photo_natural_height(sorted_media[1], col_w))
            _add_cell(sorted_media[0], body_x, y, col_w, ph_top, R, 2, 2, 2)
            _add_cell(sorted_media[1], body_x + col_w + PHOTO_GAP, y, col_w, ph_top, 2, R, 2, 2)
            y += ph_top + PHOTO_GAP
            ph_bot = max(_photo_natural_height(sorted_media[2], col_w), _photo_natural_height(sorted_media[3], col_w))
            _add_cell(sorted_media[2], body_x, y, col_w, ph_bot, 2, 2, 2, R)
            _add_cell(sorted_media[3], body_x + col_w + PHOTO_GAP, y, col_w, ph_bot, 2, 2, R, 2)
            y += ph_bot

        else:
            # stacked vertically
            for idx, photo_data in enumerate(sorted_media):
                is_first = idx == 0
                is_last = idx == total - 1
                ph = _photo_natural_height(photo_data, inner_w)
                tl = tr = R if is_first else 2
                bl = br = R if is_last else 2
                _add_cell(photo_data, body_x, y, inner_w, ph, tl, tr, br, bl)
                y += ph + (PHOTO_GAP if not is_last else 0)

        y += CARD_SECTION_GAP

    # Footer — align icon center to text cap-height center
    footer_y = y + FONT_SIZE_FOOTER
    icon_y = round(footer_y - (FONT_SIZE_FOOTER * 0.65 + X_ICON_SIZE) / 2)
    x_logo_b64 = _logo_svg_b64(_x_logo_key(theme))
    content.append(
        f'<image x="{body_x}" y="{icon_y}" width="{X_ICON_SIZE}" height="{X_ICON_SIZE}" '
        f'href="{x_logo_b64}" opacity="{FOOTER_OPACITY}"/>',
    )
    if short_url:
        display_url = short_url.removeprefix("https://").removeprefix("http://")
        content.append(
            f'<text x="{body_x + X_ICON_SIZE + 5}" y="{footer_y}" font-family="{_FONT_NAME}" font-size="{FONT_SIZE_FOOTER}" '
            f'fill="{theme.text_color}" opacity="{FOOTER_OPACITY}">{_escape(display_url)}</text>',
        )
    y += FONT_SIZE_FOOTER + CARD_INNER_PAD

    total_h = y + CARD_OUTER_PAD
    card_h = total_h - 2 * CARD_OUTER_PAD
    svg_w = card_width + 2 * CARD_OUTER_PAD

    card_rect = (
        f'<rect x="{CARD_OUTER_PAD}" y="{CARD_OUTER_PAD}" width="{card_width}" height="{card_h}" '
        f'rx="{r}" ry="{r}" fill="url(#bg)" filter="url(#shadow)"/>'
    )

    defs_svg = "<defs>" + "".join(defs) + "</defs>"
    content_svg = card_rect + "".join(content)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{total_h}">{defs_svg}{content_svg}</svg>'


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
