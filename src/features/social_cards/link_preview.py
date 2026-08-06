import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from features.images.image_color_utils import relative_luminance
from features.social_cards.card_layout import PHOTO_CORNER_RADIUS, PHOTO_GAP
from features.social_cards.card_utils import (
    FONT_NAME,
    escape_xml,
    rounded_rect_path,
    word_wrap_truncate,
)
from features.social_cards.domain import SocialLinkPreviewAsset
from features.social_cards.theme import ThemeColors
from util import log
from util.config import config

LINK_ASPECT_W = 3
LINK_ASPECT_H = 2
OVERLAY_PAD_IMAGE = 12
OVERLAY_PAD_NO_IMAGE = 18
OVERLAY_OPACITY_IMAGE = 0.55
OVERLAY_OPACITY_NO_IMAGE = 0.3
BLUR_STD_DEV = 12
TITLE_FONT_SIZE = 20
TITLE_MAX_LINES = 2
DESC_FONT_SIZE = 16
DESC_MAX_LINES = 3
DOMAIN_FONT_SIZE = 14
FAVICON_SIZE = 28
FAVICON_GAP = 8
TEXT_LINE_HEIGHT_TITLE = 26
TEXT_LINE_HEIGHT_DESC = 20
TEXT_LINE_HEIGHT_DOMAIN = 18
DESC_TOP_GAP = 8
LINK_PREVIEW_CORNER_RADIUS = 20

_OG_FETCH_TIMEOUT_S = 8
_OG_HEAD_READ_BYTES = 32 * 1024
_OG_META_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
_OG_META_RE_ALT = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.IGNORECASE)


def fetch_og_image_url(page_url: str) -> str | None:
    try:
        req = urllib.request.Request(page_url, headers = {"User-Agent": config.user_agent})
        with urllib.request.urlopen(req, timeout = _OG_FETCH_TIMEOUT_S) as resp:
            head = resp.read(_OG_HEAD_READ_BYTES).decode("utf-8", errors = "ignore")
        match = _OG_META_RE.search(head) or _OG_META_RE_ALT.search(head)
        if match:
            log.t(f"Found og:image from page: {match.group(1)}")
            return match.group(1)
    except Exception as e:
        log.t(f"OG image fetch from page failed: {e}")
    return None


_FAVICON_LINK_RE = re.compile(
    r'<link[^>]+rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def find_favicon_urls(domain: str, expanded_url: str | None = None) -> list[str]:
    urls_to_try = []
    if expanded_url:
        urls_to_try.append(expanded_url)
    urls_to_try.append(f"https://{domain}")
    favicon_urls: list[str] = []
    for page_url in urls_to_try:
        favicon_url = _find_favicon_url(page_url)
        if favicon_url and favicon_url not in favicon_urls:
            favicon_urls.append(favicon_url)
    return favicon_urls


def _find_favicon_url(page_url: str) -> str | None:
    try:
        req = urllib.request.Request(page_url, headers = {"User-Agent": config.user_agent})
        with urllib.request.urlopen(req, timeout = _OG_FETCH_TIMEOUT_S) as resp:
            final_url = resp.url
            head = resp.read(_OG_HEAD_READ_BYTES).decode("utf-8", errors = "ignore")
        matches = _FAVICON_LINK_RE.findall(head)
        for tag in matches:
            href_match = _HREF_RE.search(tag)
            if href_match:
                href = href_match.group(1)
                if href.startswith("//"):
                    return "https:" + href
                if href.startswith("/"):
                    parsed = urlparse(final_url)
                    return f"{parsed.scheme}://{parsed.hostname}{href}"
                if href.startswith("http"):
                    return href
                parsed = urlparse(final_url)
                return f"{parsed.scheme}://{parsed.hostname}/{href}"
    except Exception as e:
        log.t(f"Favicon URL extraction failed for {page_url}: {e}")
    return None


def prepare_favicon(source_path: Path, output_path: Path) -> Path | None:
    try:
        with Image.open(source_path) as source:
            img = source.convert("RGBA")
            img = img.resize((64, 64), Image.LANCZOS)
            _, _, _, a = img.split()
            gray = img.convert("LA").split()[0]
            img = Image.merge("RGBA", (gray, gray, gray, a))
            img.save(output_path, format = "PNG")
        return output_path
    except Exception as e:
        output_path.unlink(missing_ok = True)
        log.t(f"Favicon preparation failed for {source_path}: {e}")
        return None


def _dominant_color(path: Path) -> tuple[int, int, int]:
    try:
        with Image.open(path) as source:
            img = source.convert("RGB").resize((32, 32))
            quantized = img.quantize(colors = 4)
            palette = quantized.getpalette()
            if palette:
                return (palette[0], palette[1], palette[2])
    except Exception:
        pass
    return (128, 128, 128)


def _contrast_text_color(rgb: tuple[int, int, int]) -> str:
    return "#000000" if relative_luminance(rgb) > 0.5 else "#ffffff"


def _contrast_overlay_color(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return "#{:02x}{:02x}{:02x}".format(255 - r, 255 - g, 255 - b)


def _globe_icon(cx: int, cy: int, r: int, color: str, opacity: float = 0.6) -> str:
    return (
        f'<g opacity="{opacity}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<ellipse cx="{cx}" cy="{cy}" rx="{r * 0.5}" ry="{r}" fill="none" stroke="{color}" stroke-width="0.8"/>'
        f'<line x1="{cx - r}" y1="{cy}" x2="{cx + r}" y2="{cy}" stroke="{color}" stroke-width="0.8"/>'
        f'<path d="M{cx - r + 1},{cy - r * 0.5} Q{cx},{cy - r * 0.35} {cx + r - 1},{cy - r * 0.5}" '
        f'fill="none" stroke="{color}" stroke-width="0.7"/>'
        f'<path d="M{cx - r + 1},{cy + r * 0.5} Q{cx},{cy + r * 0.35} {cx + r - 1},{cy + r * 0.5}" '
        f'fill="none" stroke="{color}" stroke-width="0.7"/>'
        f"</g>"
    )


def render_link_previews(
    link_previews: list[SocialLinkPreviewAsset],
    x: int,
    y: int,
    width: int,
    theme: ThemeColors,
) -> tuple[list[str], list[str], int]:
    defs: list[str] = []
    content: list[str] = []
    cur_y = y

    for i, preview_asset in enumerate(link_previews):
        preview = preview_asset.link_preview
        title = preview.title or ""
        description = preview.description or ""
        domain = preview.domain
        uid = f"lp-{i}"

        if preview_asset.og_image_path:
            d, c, h = _render_with_image(
                uid, x, cur_y, width, title, description, domain,
                preview_asset.og_image_path, preview_asset.favicon_path,
            )
        else:
            d, c, h = _render_without_image(
                x, cur_y, width, title, description, domain,
                preview_asset.favicon_path, theme,
            )

        defs.extend(d)
        content.extend(c)
        cur_y += h + PHOTO_GAP

    total_h = cur_y - y - (PHOTO_GAP if link_previews else 0)
    return defs, content, total_h


def _render_with_image(
    uid: str,
    x: int,
    y: int,
    width: int,
    title: str,
    description: str,
    domain: str,
    og_image_path: Path,
    favicon_path: Path | None,
) -> tuple[list[str], list[str], int]:
    defs: list[str] = []
    content: list[str] = []

    pad = OVERLAY_PAD_NO_IMAGE
    R = PHOTO_CORNER_RADIUS
    fav_size = FAVICON_SIZE

    header_text_w = width - 2 * pad - fav_size - FAVICON_GAP
    desc_text_w = width - 2 * pad

    title_lines = word_wrap_truncate(title, header_text_w, TITLE_FONT_SIZE, 1) if title else []
    desc_lines = word_wrap_truncate(description, desc_text_w, DESC_FONT_SIZE, DESC_MAX_LINES) if description else []
    header_h = TEXT_LINE_HEIGHT_TITLE + TEXT_LINE_HEIGHT_DOMAIN
    desc_h = len(desc_lines) * TEXT_LINE_HEIGHT_DESC
    overlay_h = 2 * pad + header_h + DESC_TOP_GAP + desc_h

    total_h = round(width * LINK_ASPECT_H / LINK_ASPECT_W)
    if overlay_h > total_h:
        total_h = overlay_h + pad
    overlay_y = y + total_h - overlay_h

    # Clip for entire box
    box_clip_id = f"{uid}-box-clip"
    box_path = rounded_rect_path(x, y, width, total_h, R, R, R, R)
    defs.append(f'<clipPath id="{box_clip_id}"><path d="{box_path}"/></clipPath>')

    # OG image (sharp, full box)
    content.append(
        f'<image clip-path="url(#{box_clip_id})" x="{x}" y="{y}" width="{width}" height="{total_h}" '
        f'href="{escape_xml(str(og_image_path.resolve()))}" preserveAspectRatio="xMidYMid slice"/>',
    )

    # Overlay region (bottom of card)
    overlay_actual_h = total_h - (overlay_y - y)
    overlay_path = rounded_rect_path(x, overlay_y, width, overlay_actual_h, 0, 0, R, R)

    dominant = _dominant_color(og_image_path)
    text_color = _contrast_text_color(dominant)
    overlay_fill = "#000000" if text_color == "#ffffff" else "#ffffff"

    # Colored overlay panel (no blur — resvg can't composite filter+clip correctly)
    content.append(
        f'<path clip-path="url(#{box_clip_id})" d="{overlay_path}" '
        f'fill="{overlay_fill}" fill-opacity="0.6"/>',
    )

    # Layout: favicon on left spanning title+domain, text on right, desc below full width
    fav_x = x + pad
    text_x = fav_x + fav_size + FAVICON_GAP
    cur_y = overlay_y + pad
    fav_y = cur_y + (header_h - fav_size) // 2

    if favicon_path:
        content.append(
            f'<image x="{fav_x}" y="{fav_y}" width="{fav_size}" height="{fav_size}" '
            f'href="{escape_xml(str(favicon_path.resolve()))}" preserveAspectRatio="xMidYMid slice"/>',
        )
    else:
        globe_cx = fav_x + fav_size // 2
        globe_cy = fav_y + fav_size // 2
        globe_r = round(fav_size * 0.35)
        content.append(_globe_icon(globe_cx, globe_cy, globe_r, text_color, 1.0))

    # Title (bold, 1 line) next to favicon
    cur_y += TITLE_FONT_SIZE
    if title_lines:
        content.append(
            f'<text x="{text_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{TITLE_FONT_SIZE}" '
            f'fill="{text_color}" stroke="{text_color}" stroke-width="0.5" paint-order="stroke" '
            f'xml:space="preserve">{escape_xml(title_lines[0])}</text>',
        )
    cur_y += TEXT_LINE_HEIGHT_TITLE - TITLE_FONT_SIZE

    # Domain next to favicon
    cur_y += DOMAIN_FONT_SIZE
    content.append(
        f'<text x="{text_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{DOMAIN_FONT_SIZE}" '
        f'fill="{text_color}" fill-opacity="0.6" xml:space="preserve">{escape_xml(domain)}</text>',
    )
    cur_y += TEXT_LINE_HEIGHT_DOMAIN - DOMAIN_FONT_SIZE

    # Description full width below
    cur_y += DESC_TOP_GAP
    desc_x = x + pad
    for line in desc_lines:
        cur_y += DESC_FONT_SIZE
        content.append(
            f'<text x="{desc_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{DESC_FONT_SIZE}" '
            f'fill="{text_color}" fill-opacity="0.8" xml:space="preserve">{escape_xml(line)}</text>',
        )
        cur_y += TEXT_LINE_HEIGHT_DESC - DESC_FONT_SIZE

    return defs, content, total_h


def _render_without_image(
    x: int,
    y: int,
    width: int,
    title: str,
    description: str,
    domain: str,
    favicon_path: Path | None,
    theme: ThemeColors,
) -> tuple[list[str], list[str], int]:
    content: list[str] = []

    pad = OVERLAY_PAD_NO_IMAGE
    fav_size = FAVICON_SIZE
    full_w = width - 2 * pad
    header_text_w = full_w - fav_size - FAVICON_GAP

    desc_lines = word_wrap_truncate(description, full_w, DESC_FONT_SIZE, DESC_MAX_LINES) if description else []
    header_h = TEXT_LINE_HEIGHT_TITLE + TEXT_LINE_HEIGHT_DOMAIN
    desc_h = len(desc_lines) * TEXT_LINE_HEIGHT_DESC
    total_h = 2 * pad + header_h + DESC_TOP_GAP + desc_h

    R = LINK_PREVIEW_CORNER_RADIUS
    hex_bg = theme.gradient_start.lstrip("#")
    bg_r, bg_g, bg_b = int(hex_bg[0:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
    overlay_fill = _contrast_overlay_color((bg_r, bg_g, bg_b))
    text_color = _contrast_text_color((bg_r, bg_g, bg_b))

    rect_path = rounded_rect_path(x, y, width, total_h, R, R, R, R)
    content.append(f'<path d="{rect_path}" fill="{overlay_fill}" fill-opacity="{OVERLAY_OPACITY_NO_IMAGE}"/>')

    cur_y = y + pad
    fav_x = x + pad
    fav_y = cur_y + (header_h - fav_size) // 2

    if favicon_path:
        content.append(
            f'<image x="{fav_x}" y="{fav_y}" width="{fav_size}" height="{fav_size}" '
            f'href="{escape_xml(str(favicon_path.resolve()))}" preserveAspectRatio="xMidYMid slice"/>',
        )
    else:
        globe_cx = fav_x + fav_size // 2
        globe_cy = fav_y + fav_size // 2
        globe_r = round(fav_size * 0.35)
        content.append(_globe_icon(globe_cx, globe_cy, globe_r, text_color, 1.0))

    # Title (bold, 1 line) next to favicon
    text_x = fav_x + fav_size + FAVICON_GAP
    cur_y += TITLE_FONT_SIZE
    if title:
        title_lines = word_wrap_truncate(title, header_text_w, TITLE_FONT_SIZE, 1)
        content.append(
            f'<text x="{text_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{TITLE_FONT_SIZE}" '
            f'fill="{text_color}" stroke="{text_color}" stroke-width="0.5" paint-order="stroke" '
            f'xml:space="preserve">{escape_xml(title_lines[0])}</text>',
        )
    cur_y += TEXT_LINE_HEIGHT_TITLE - TITLE_FONT_SIZE

    # Domain/URL next to favicon
    cur_y += DOMAIN_FONT_SIZE
    content.append(
        f'<text x="{text_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{DOMAIN_FONT_SIZE}" '
        f'fill="{text_color}" fill-opacity="0.6" xml:space="preserve">{escape_xml(domain)}</text>',
    )
    cur_y += TEXT_LINE_HEIGHT_DOMAIN - DOMAIN_FONT_SIZE

    # Gap before description
    cur_y += DESC_TOP_GAP

    # Description full width below
    desc_x = x + pad
    for line in desc_lines:
        cur_y += DESC_FONT_SIZE
        content.append(
            f'<text x="{desc_x}" y="{cur_y}" font-family="{FONT_NAME}" font-size="{DESC_FONT_SIZE}" '
            f'fill="{text_color}" fill-opacity="0.8" xml:space="preserve">{escape_xml(line)}</text>',
        )
        cur_y += TEXT_LINE_HEIGHT_DESC - DESC_FONT_SIZE

    return [], content, total_h
