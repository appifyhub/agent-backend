import re
from pathlib import Path

from PIL import Image

from features.images.image_color_utils import relative_luminance
from features.social_cards.card_utils import (
    FONT_NAME,
    emoji_split,
    escape_xml,
    render_text_segments,
    rounded_rect_path,
    word_wrap_truncate,
)
from features.social_cards.domain import SocialPost, SocialPostRenderAssets
from features.social_cards.theme import ThemeColors

EMBED_PAD = 20
EMBED_AVATAR_SIZE = 36
EMBED_AVATAR_GAP = 10
EMBED_NAME_FONT_SIZE = 16
EMBED_BODY_FONT_SIZE = 18
EMBED_BODY_LINE_HEIGHT = 24
EMBED_BODY_MAX_LINES = 4
EMBED_PHOTO_MAX_H = 160
EMBED_PHOTO_CORNER_RADIUS = 12
EMBED_CORNER_RADIUS = 28
EMBED_SECTION_GAP = 10
EMBED_OVERLAY_OPACITY = 0.15

_URL_RE = re.compile(r"https?://\S+")


def render_embedded_post(
    post: SocialPost,
    x: int,
    y: int,
    width: int,
    theme: ThemeColors,
    assets: SocialPostRenderAssets,
) -> tuple[list[str], list[str], int]:
    defs: list[str] = []
    content: list[str] = []

    R = EMBED_CORNER_RADIUS
    pad = EMBED_PAD
    inner_w = width - 2 * pad

    clean_text = _URL_RE.sub("", post.text).strip()
    clean_text = re.sub(r" +", " ", clean_text)

    body_lines = word_wrap_truncate(clean_text, inner_w, EMBED_BODY_FONT_SIZE, EMBED_BODY_MAX_LINES)
    body_h = len(body_lines) * EMBED_BODY_LINE_HEIGHT

    photo_h = 0
    photo_path: Path | None = None
    photo_display_w = inner_w
    media_path = assets.media[0].path if assets.media else None
    if media_path:
        try:
            with Image.open(media_path) as img:
                natural_h = round(photo_display_w * img.height / img.width) if img.width > 0 else photo_display_w
                photo_h = min(natural_h, EMBED_PHOTO_MAX_H)
                photo_path = media_path
        except Exception:
            pass

    header_h = EMBED_AVATAR_SIZE
    total_h = pad + header_h + EMBED_SECTION_GAP + body_h
    if photo_h > 0:
        total_h += EMBED_SECTION_GAP + photo_h
    total_h += pad

    # Background rect
    hex_bg = theme.gradient_start.lstrip("#")
    bg_r, bg_g, bg_b = int(hex_bg[0:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
    overlay_fill = "#ffffff" if relative_luminance((bg_r, bg_g, bg_b)) < 0.5 else "#000000"

    rect_path = rounded_rect_path(x, y, width, total_h, R, R, R, R)
    content.append(f'<path d="{rect_path}" fill="{overlay_fill}" fill-opacity="{EMBED_OVERLAY_OPACITY}"/>')

    cur_y = y + pad

    # Avatar
    av_x = x + pad
    av_cy = cur_y + EMBED_AVATAR_SIZE // 2
    av_cx = av_x + EMBED_AVATAR_SIZE // 2
    clip_id = "embed-avatar-clip"
    defs.append(f'<clipPath id="{clip_id}"><circle cx="{av_cx}" cy="{av_cy}" r="{EMBED_AVATAR_SIZE // 2}"/></clipPath>')

    if assets.avatar_path:
        content.append(
            f'<image clip-path="url(#{clip_id})" x="{av_x}" y="{cur_y}" '
            f'width="{EMBED_AVATAR_SIZE}" height="{EMBED_AVATAR_SIZE}" '
            f'href="{escape_xml(str(assets.avatar_path.resolve()))}" preserveAspectRatio="xMidYMid slice"/>',
        )
    else:
        initial = (post.author.handle or "?")[0].upper()
        content.append(
            f'<circle cx="{av_cx}" cy="{av_cy}" r="{EMBED_AVATAR_SIZE // 2}" fill="{theme.text_color}" fill-opacity="0.2"/>'
            f'<text x="{av_cx}" y="{av_cy + 5}" text-anchor="middle" font-family="{FONT_NAME}" '
            f'font-size="{EMBED_AVATAR_SIZE // 2}" fill="{theme.text_color}">{initial}</text>',
        )

    # Name
    name_x = av_x + EMBED_AVATAR_SIZE + EMBED_AVATAR_GAP
    name_y = cur_y + (EMBED_AVATAR_SIZE + EMBED_NAME_FONT_SIZE) // 2 - 2
    display_name = post.author.display_name or f"@{post.author.handle}"
    max_name_w = inner_w - EMBED_AVATAR_SIZE - EMBED_AVATAR_GAP
    name_lines = word_wrap_truncate(display_name, max_name_w, EMBED_NAME_FONT_SIZE, 1)
    name_segments = [(sub, theme.text_color, "", is_emoji) for sub, is_emoji in emoji_split(name_lines[0]) if sub]
    name_elems, _ = render_text_segments(name_segments, name_x, name_y, EMBED_NAME_FONT_SIZE, theme.text_color, weight = 700)
    content.extend(name_elems)

    cur_y += header_h + EMBED_SECTION_GAP

    # Body text
    text_x = x + pad
    for line in body_lines:
        cur_y += EMBED_BODY_FONT_SIZE
        segments = [(sub, theme.text_color, "", is_emoji) for sub, is_emoji in emoji_split(line) if sub]
        line_elems, _ = render_text_segments(segments, text_x, cur_y, EMBED_BODY_FONT_SIZE, theme.text_color)
        content.extend(line_elems)
        cur_y += EMBED_BODY_LINE_HEIGHT - EMBED_BODY_FONT_SIZE

    # Photo (optional, max 1)
    if photo_h > 0 and photo_path:
        cur_y += EMBED_SECTION_GAP
        photo_x = x + pad
        PR = EMBED_PHOTO_CORNER_RADIUS
        photo_clip_id = "embed-photo-clip"
        photo_clip_path = rounded_rect_path(photo_x, cur_y, photo_display_w, photo_h, PR, PR, PR, PR)
        defs.append(f'<clipPath id="{photo_clip_id}"><path d="{photo_clip_path}"/></clipPath>')
        content.append(
            f'<image clip-path="url(#{photo_clip_id})" x="{photo_x}" y="{cur_y}" '
            f'width="{photo_display_w}" height="{photo_h}" '
            f'href="{escape_xml(str(photo_path.resolve()))}" preserveAspectRatio="xMidYMid slice"/>',
        )

    return defs, content, total_h
