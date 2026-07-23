from pathlib import Path

import resvg_py

from features.social_cards.card_layout import card_width_from_text
from features.social_cards.card_template import build_svg
from features.social_cards.domain import SocialPost, SocialPostRenderAssets
from features.social_cards.theme import ThemeColors
from util.config import config

_FONTS_DIR = Path(config.fonts_dir)


def render(
    post: SocialPost,
    theme: ThemeColors,
    assets: SocialPostRenderAssets,
    short_url: str | None = None,
) -> bytes:
    card_width = card_width_from_text(post.text)
    svg = build_svg(
        post = post,
        theme = theme,
        card_width = card_width,
        assets = assets,
        short_url = short_url,
    )
    font_files = [str(p) for p in _FONTS_DIR.glob("*.ttf") if p.is_file()]
    return resvg_py.svg_to_bytes(
        svg_string = svg,
        font_files = font_files,
        skip_system_fonts = True,
    )
