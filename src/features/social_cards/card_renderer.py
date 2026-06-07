from pathlib import Path

import resvg_py

from features.social_cards.card_layout import card_width_from_text
from features.social_cards.card_template import build_svg
from features.social_cards.theme import ThemeColors
from features.web_browsing.twitter_status_fetcher import TweetData
from util.config import config

_FONTS_DIR = Path(config.fonts_dir)


def render(
    tweet: TweetData,
    theme: ThemeColors,
    profile_bytes: bytes | None = None,
    media_bytes: list[bytes] | None = None,
    short_url: str | None = None,
    link_preview_data: list[dict] | None = None,
    quoted_tweet_data: dict | None = None,
) -> bytes:
    media = media_bytes or []
    card_width = card_width_from_text(tweet.text)
    svg = build_svg(
        tweet = tweet,
        theme = theme,
        card_width = card_width,
        profile_bytes = profile_bytes,
        media_bytes = media,
        short_url = short_url,
        link_preview_data = link_preview_data or [],
        quoted_tweet_data = quoted_tweet_data,
    )
    font_files = [str(p) for p in _FONTS_DIR.glob("*.ttf") if p.is_file()]
    return resvg_py.svg_to_bytes(
        svg_string = svg,
        font_files = font_files,
        skip_system_fonts = True,
    )
