import base64
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from features.images.image_color_utils import relative_luminance
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
    PLATFORM_ICON_SIZE,
)
from features.social_cards.card_utils import (
    FONT_NAME,
    FONT_PATH,
    emoji_split,
    escape_xml,
    render_text_segments,
    rounded_rect_path,
    text_width,
)
from features.social_cards.domain import (
    SocialCardTemplateResult,
    SocialMediaAsset,
    SocialMediaPlacement,
    SocialPost,
    SocialPostRenderAssets,
)
from features.social_cards.embedded_post import render_embedded_post
from features.social_cards.link_preview import render_link_previews
from features.social_cards.theme import ThemeColors
from util.config import config

_FONT_B64: str | None = None
_LOGO_CACHE: dict[str, bytes] = {}

_SPECIAL_TOKEN_RE = re.compile(r"(https?://\S+|www\.\S+|@\w+|#\w+|\$[A-Za-z]+)")


def _font_b64() -> str:
    global _FONT_B64
    if _FONT_B64 is None:
        _FONT_B64 = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    return _FONT_B64


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
    luminance = relative_luminance((r, g, b))
    if luminance < 0.3:
        return "agent_logo_light"
    if luminance > 0.7:
        return "agent_logo_dark"
    return "agent_logo_color"


def _platform_logo_key(post: SocialPost, theme: ThemeColors) -> str:
    return post.platform.logo_light_key if theme.text_color == "#ffffff" else post.platform.logo_dark_key


def _accent_color(theme: ThemeColors) -> str:
    h = theme.gradient_start.lstrip("#")
    r, g, b = 255 - int(h[0:2], 16), 255 - int(h[2:4], 16), 255 - int(h[4:6], 16)
    return f"#{r:02x}{g:02x}{b:02x}"


def _photo_natural_height(path: Path, display_w: int) -> int:
    try:
        with Image.open(path) as img:
            if img.width == 0:
                return display_w
            return round(display_w * img.height / img.width)
    except Exception:
        return display_w


def _photo_sort_key(path: Path) -> int:
    try:
        with Image.open(path) as img:
            if img.height > img.width * 1.05:
                return 0  # portrait first
            if img.width > img.height * 1.05:
                return 2  # landscape last
            return 1  # square middle
    except Exception:
        return 1


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
            if text_width(candidate, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def _line_to_segments(line: str, normal_fill: str, accent: str) -> list[tuple[str, str, str, bool]]:
    segments: list[tuple[str, str, str, bool]] = []
    parts = _SPECIAL_TOKEN_RE.split(line)
    for i, part in enumerate(parts):
        if not part:
            continue
        is_special = i % 2 == 1
        fill = accent if is_special else normal_fill
        decoration = ' text-decoration="underline"' if is_special else ""
        for sub_text, is_emoji in emoji_split(part):
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


def _photo_cell_parts(
    cell_id: str,
    x: int,
    y: int,
    w: int,
    h: int,
    photo_href: str,
    tl: int,
    tr: int,
    br: int,
    bl: int,
) -> tuple[str, str]:
    path = rounded_rect_path(x, y, w, h, tl, tr, br, bl)
    clip = f'<clipPath id="{cell_id}-clip"><path d="{path}"/></clipPath>'
    img = (
        f'<image clip-path="url(#{cell_id}-clip)" x="{x}" y="{y}" width="{w}" height="{h}" '
        f'href="{photo_href}" preserveAspectRatio="xMidYMid slice"/>'
    )
    return clip, img


def build_svg(
    post: SocialPost,
    theme: ThemeColors,
    card_width: int,
    assets: SocialPostRenderAssets,
    short_url: str | None,
) -> SocialCardTemplateResult:
    cx = CARD_OUTER_PAD  # card left edge
    inner_w = card_width - 2 * CARD_INNER_PAD
    body_x = cx + CARD_INNER_PAD
    r = CARD_CORNER_RADIUS
    accent = _accent_color(theme)

    defs: list[str] = []
    content: list[str] = []
    media_placements: list[SocialMediaPlacement] = []

    # Font
    defs.append(
        f'<style type="text/css">'
        f'@font-face {{font-family:"{FONT_NAME}";font-style:normal;font-weight:100 900;'
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
    if assets.avatar_path:
        content.append(
            f'<image clip-path="url(#avatar-clip)" x="{cx + CARD_INNER_PAD}" y="{y}" '
            f'width="{AVATAR_SIZE}" height="{AVATAR_SIZE}" href="{escape_xml(str(assets.avatar_path.resolve()))}" '
            f'preserveAspectRatio="xMidYMid slice"/>',
        )
    else:
        initial = (post.author.handle or "?")[0].upper()
        content.append(
            f'<circle cx="{av_cx}" cy="{av_cy_center}" r="{AVATAR_SIZE // 2}" fill="{theme.text_color}" fill-opacity="0.2"/>'
            f'<text x="{av_cx}" y="{av_cy_center + 8}" text-anchor="middle" font-family="{FONT_NAME}" '
            f'font-size="{AVATAR_SIZE // 2}" fill="{theme.text_color}">{initial}</text>',
        )

    name_x = cx + CARD_INNER_PAD + AVATAR_SIZE + AVATAR_GAP
    _name_date_span = FONT_SIZE_DATE + 8
    _visual_block_h = FONT_SIZE_NAME + _name_date_span
    name_y = y + (AVATAR_SIZE + _visual_block_h) // 2 - _name_date_span
    date_y = name_y + _name_date_span

    def _name_segments(text: str) -> list[tuple[str, str, str, bool]]:
        return [(sub, theme.text_color, "", is_emoji) for sub, is_emoji in emoji_split(text) if sub]

    if post.author.display_name:
        name_elems, name_end_x = render_text_segments(
            _name_segments(post.author.display_name), name_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 700,
        )
        content.extend(name_elems)
        handle_elems, _ = render_text_segments(
            _name_segments(f" (@{post.author.handle})"), name_end_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 400,
        )
        content.extend(handle_elems)
    else:
        handle_elems, _ = render_text_segments(
            _name_segments(f"@{post.author.handle}"), name_x, name_y, FONT_SIZE_NAME, theme.text_color, weight = 700,
        )
        content.extend(handle_elems)
    dt_str = _format_datetime(post.created_at)
    if dt_str:
        content.append(
            f'<text x="{name_x}" y="{date_y}" font-family="{FONT_NAME}" font-size="{FONT_SIZE_DATE}" '
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

    # Embedded post (above body text) — replaces divider
    if post.embedded_post and assets.embedded_post:
        quote_line_w = 4
        quote_line_gap = 12
        embed_x = body_x + quote_line_w + quote_line_gap
        embed_w = inner_w - quote_line_w - quote_line_gap
        ep_defs, ep_content, ep_height = render_embedded_post(
            post = post.embedded_post,
            x = embed_x,
            y = y,
            width = embed_w,
            theme = theme,
            assets = assets.embedded_post,
        )
        defs.extend(ep_defs)
        line_inset = round(ep_height * 0.05)
        line_h = ep_height - 2 * line_inset
        content.append(
            f'<rect x="{body_x}" y="{y + line_inset}" width="{quote_line_w}" height="{line_h}" '
            f'rx="2" fill="{theme.text_color}" fill-opacity="0.3"/>',
        )
        content.extend(ep_content)
        y += ep_height + CARD_SECTION_GAP
    else:
        # Divider (only when no embedded post)
        content.append(
            f'<line x1="{body_x}" y1="{y}" x2="{body_x + inner_w}" y2="{y}" '
            f'stroke="{theme.text_color}" stroke-opacity="{DIVIDER_OPACITY}" stroke-width="1"/>',
        )
        y += CARD_SECTION_GAP

    # Post body with colored tokens
    lines = _word_wrap(post.text, inner_w, FONT_SIZE_BODY)
    if lines:
        for i, ln in enumerate(lines):
            line_y = y + FONT_SIZE_BODY + i * LINE_HEIGHT_BODY
            segments = _line_to_segments(ln, theme.text_color, accent)
            if not segments:
                continue
            line_elems, _ = render_text_segments(segments, body_x, line_y, FONT_SIZE_BODY, theme.text_color)
            content.extend(line_elems)
        y += len(lines) * LINE_HEIGHT_BODY + CARD_SECTION_GAP

    # Link previews (above photos)
    if assets.link_previews:
        lp_defs, lp_content, lp_height = render_link_previews(
            link_previews = assets.link_previews,
            x = body_x,
            y = y,
            width = inner_w,
            theme = theme,
        )
        defs.extend(lp_defs)
        content.extend(lp_content)
        if lp_height > 0:
            y += lp_height + CARD_SECTION_GAP

    # Dynamic media — source order, full-width rows
    dynamic_media = [asset for asset in assets.media if asset.media.dynamic_media]
    cell = 0  # global cell index for unique clip-path IDs

    def _add_cell(
        asset: SocialMediaAsset,
        cell_x: int,
        cell_y: int,
        width: int,
        height: int,
        top_left: int,
        top_right: int,
        bottom_right: int,
        bottom_left: int,
    ) -> None:
        nonlocal cell
        clip, image = _photo_cell_parts(
            f"photo-{cell}",
            cell_x,
            cell_y,
            width,
            height,
            escape_xml(str(asset.path.resolve())),
            top_left,
            top_right,
            bottom_right,
            bottom_left,
        )
        defs.append(clip)
        content.append(image)
        media_placements.append(
            SocialMediaPlacement(
                media = asset.media,
                x = cell_x,
                y = cell_y,
                width = width,
                height = height,
                top_left_radius = top_left,
                top_right_radius = top_right,
                bottom_right_radius = bottom_right,
                bottom_left_radius = bottom_left,
            ),
        )
        cell += 1

    for asset in dynamic_media:
        media_height = _photo_natural_height(asset.path, inner_w)
        _add_cell(
            asset,
            body_x,
            y,
            inner_w,
            media_height,
            PHOTO_CORNER_RADIUS,
            PHOTO_CORNER_RADIUS,
            PHOTO_CORNER_RADIUS,
            PHOTO_CORNER_RADIUS,
        )
        y += media_height + PHOTO_GAP
    if dynamic_media:
        y += CARD_SECTION_GAP - PHOTO_GAP

    # Photos — sorted portrait → square → landscape
    photo_media = [asset for asset in assets.media if not asset.media.dynamic_media]
    if photo_media:
        sorted_media = sorted(photo_media, key = lambda asset: _photo_sort_key(asset.path))
        total = len(sorted_media)
        keys = [_photo_sort_key(asset.path) for asset in sorted_media]
        n_portrait = keys.count(0)

        R = PHOTO_CORNER_RADIUS

        if total == 2 and all(k <= 1 for k in keys):
            # 2 portrait/square → side by side
            col_w = (inner_w - PHOTO_GAP) // 2
            ph = max(
                _photo_natural_height(sorted_media[0].path, col_w),
                _photo_natural_height(sorted_media[1].path, col_w),
            )
            _add_cell(sorted_media[0], body_x, y, col_w, ph, R, 2, 2, R)
            _add_cell(sorted_media[1], body_x + col_w + PHOTO_GAP, y, col_w, ph, 2, R, R, 2)
            y += ph

        elif total == 3 and n_portrait == 3:
            # 3 portraits → 3 columns
            col_w = (inner_w - 2 * PHOTO_GAP) // 3
            ph = max(_photo_natural_height(asset.path, col_w) for asset in sorted_media)
            for i, asset in enumerate(sorted_media):
                x_off = body_x + i * (col_w + PHOTO_GAP)
                tl = R if i == 0 else 2
                bl = R if i == 0 else 2
                tr = R if i == 2 else 2
                br = R if i == 2 else 2
                _add_cell(asset, x_off, y, col_w, ph, tl, tr, br, bl)
            y += ph

        elif total == 3 and n_portrait == 2 and keys.count(1) == 1:
            # 2 portraits + 1 square → portraits side by side on top, square full-width below
            portraits = [d for d, k in zip(sorted_media, keys) if k == 0]
            square = next(d for d, k in zip(sorted_media, keys) if k == 1)
            col_w = (inner_w - PHOTO_GAP) // 2
            ph_top = max(
                _photo_natural_height(portraits[0].path, col_w),
                _photo_natural_height(portraits[1].path, col_w),
            )
            _add_cell(portraits[0], body_x, y, col_w, ph_top, R, 2, 2, 2)
            _add_cell(portraits[1], body_x + col_w + PHOTO_GAP, y, col_w, ph_top, 2, R, 2, 2)
            y += ph_top + PHOTO_GAP
            ph_bot = _photo_natural_height(square.path, inner_w)
            _add_cell(square, body_x, y, inner_w, ph_bot, 2, 2, R, R)
            y += ph_bot

        elif total == 4 and n_portrait == 4:
            # 4 portraits → 2×2 grid
            col_w = (inner_w - PHOTO_GAP) // 2
            ph_top = max(
                _photo_natural_height(sorted_media[0].path, col_w),
                _photo_natural_height(sorted_media[1].path, col_w),
            )
            _add_cell(sorted_media[0], body_x, y, col_w, ph_top, R, 2, 2, 2)
            _add_cell(sorted_media[1], body_x + col_w + PHOTO_GAP, y, col_w, ph_top, 2, R, 2, 2)
            y += ph_top + PHOTO_GAP
            ph_bot = max(
                _photo_natural_height(sorted_media[2].path, col_w),
                _photo_natural_height(sorted_media[3].path, col_w),
            )
            _add_cell(sorted_media[2], body_x, y, col_w, ph_bot, 2, 2, 2, R)
            _add_cell(sorted_media[3], body_x + col_w + PHOTO_GAP, y, col_w, ph_bot, 2, 2, R, 2)
            y += ph_bot

        else:
            # stacked vertically
            for idx, asset in enumerate(sorted_media):
                is_first = idx == 0
                is_last = idx == total - 1
                ph = _photo_natural_height(asset.path, inner_w)
                tl = tr = R if is_first else 2
                bl = br = R if is_last else 2
                _add_cell(asset, body_x, y, inner_w, ph, tl, tr, br, bl)
                y += ph + (PHOTO_GAP if not is_last else 0)

        y += CARD_SECTION_GAP

    # Footer — align icon center to text cap-height center
    footer_y = y + FONT_SIZE_FOOTER
    icon_y = round(footer_y - (FONT_SIZE_FOOTER * 0.65 + PLATFORM_ICON_SIZE) / 2)
    platform_logo_b64 = _logo_svg_b64(_platform_logo_key(post, theme))
    content.append(
        f'<image x="{body_x}" y="{icon_y}" width="{PLATFORM_ICON_SIZE}" height="{PLATFORM_ICON_SIZE}" '
        f'href="{platform_logo_b64}" opacity="{FOOTER_OPACITY}"/>',
    )
    if short_url:
        display_url = short_url.removeprefix("https://").removeprefix("http://")
        content.append(
            f'<text x="{body_x + PLATFORM_ICON_SIZE + 5}" y="{footer_y}" font-family="{FONT_NAME}" font-size="{FONT_SIZE_FOOTER}" '  # noqa: E501
            f'fill="{theme.text_color}" opacity="{FOOTER_OPACITY}">{escape_xml(display_url)}</text>',
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
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{total_h}">{defs_svg}{content_svg}</svg>'
    return SocialCardTemplateResult(
        svg = svg,
        width = svg_w,
        height = total_h,
        media_placements = media_placements,
    )
