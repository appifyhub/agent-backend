from datetime import datetime, timedelta

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.social_cards import card_renderer
from features.social_cards.link_preview import fetch_favicon, fetch_og_image_url
from features.social_cards.theme import pick_theme
from features.web_browsing.photo_downloader import PhotoDownloader
from features.web_browsing.twitter_utils import resolve_tweet_id
from util import log
from util.error_codes import IMAGE_GENERATION_FAILED, WEB_FETCH_FAILED
from util.errors import ExternalServiceError, ValidationError


class SocialCardOrchestrator:

    TOOL_TYPE: ToolType = ToolType.api_twitter
    VISION_TOOL_TYPE: ToolType = ToolType.vision

    __x_api_tool: ConfiguredTool
    __vision_tool: ConfiguredTool
    __di: DI

    def __init__(self, x_api_tool: ConfiguredTool, vision_tool: ConfiguredTool, di: DI):
        self.__x_api_tool = x_api_tool
        self.__vision_tool = vision_tool
        self.__di = di

    def execute(self, url: str) -> str:
        tweet_id = resolve_tweet_id(url)
        if not tweet_id:
            raise ValidationError(f"Cannot resolve tweet ID from URL: {url}", WEB_FETCH_FAILED)

        fetcher = self.__di.twitter_status_fetcher(tweet_id, self.__x_api_tool, self.__vision_tool)
        tweet = fetcher.as_structured()

        downloader = PhotoDownloader()

        profile_bytes: bytes | None = None
        if tweet.user.profile_image_url:
            bigger_url = tweet.user.profile_image_url.replace("_normal", "_bigger")
            profile_bytes = downloader.download(bigger_url)

        media_urls = [m.url or m.preview_url for m in tweet.media if m.url or m.preview_url]
        media_bytes = downloader.download_many([u for u in media_urls if u])

        # Fetch link preview assets
        has_tweet_media = bool(media_bytes)
        link_preview_data: list[dict] = []
        for lp in tweet.link_previews:
            og_image_bytes: bytes | None = None
            if not has_tweet_media:
                if lp.og_image_url:
                    og_image_bytes = downloader.download(lp.og_image_url)
                if not og_image_bytes:
                    fallback_url = fetch_og_image_url(lp.expanded_url)
                    if fallback_url:
                        og_image_bytes = downloader.download(fallback_url)
            favicon_bytes = fetch_favicon(lp.domain, expanded_url = lp.expanded_url)
            short_link: str | None = None
            try:
                valid_until = datetime.now() + timedelta(days = 365)
                short_link = self.__di.url_shortener(lp.expanded_url, valid_until = valid_until).execute()
            except Exception as e:
                log.w("Link preview URL shortening failed", e)
                short_link = lp.expanded_url
            link_preview_data.append({
                "title": lp.title,
                "description": lp.description,
                "domain": lp.domain,
                "og_image_bytes": og_image_bytes,
                "favicon_bytes": favicon_bytes,
                "short_url": short_link,
            })

        # Fetch referenced tweet (quoted or replied-to) if present
        quoted_tweet_data: dict | None = None
        referenced_id = tweet.quoted_tweet_id or tweet.replied_to_tweet_id
        if referenced_id:
            try:
                qt_fetcher = self.__di.twitter_status_fetcher(referenced_id, self.__x_api_tool, self.__vision_tool)
                qt_tweet = qt_fetcher.as_structured()
                qt_profile_bytes: bytes | None = None
                if qt_tweet.user.profile_image_url:
                    qt_bigger_url = qt_tweet.user.profile_image_url.replace("_normal", "_bigger")
                    qt_profile_bytes = downloader.download(qt_bigger_url)
                qt_media_bytes: bytes | None = None
                qt_media_urls = [m.url or m.preview_url for m in qt_tweet.media if m.url or m.preview_url]
                if qt_media_urls:
                    qt_media_bytes = downloader.download(qt_media_urls[0])
                quoted_tweet_data = {
                    "tweet": qt_tweet,
                    "profile_bytes": qt_profile_bytes,
                    "media_bytes": qt_media_bytes,
                }
            except Exception as e:
                log.w(f"Failed to fetch referenced tweet {referenced_id}", e)

        theme = pick_theme(profile_bytes, media_bytes)

        short_url: str | None = None
        try:
            valid_until = datetime.now() + timedelta(days = 365)
            short_url = self.__di.url_shortener(url, valid_until = valid_until).execute()
        except Exception as e:
            log.w("URL shortening failed, using original URL", e)
            short_url = url

        try:
            png_bytes = card_renderer.render(
                tweet = tweet,
                theme = theme,
                profile_bytes = profile_bytes,
                media_bytes = media_bytes,
                short_url = short_url,
                link_preview_data = link_preview_data,
                quoted_tweet_data = quoted_tweet_data,
            )
        except Exception as e:
            raise ExternalServiceError("Card rendering failed", IMAGE_GENERATION_FAILED) from e

        return self.__di.image_uploader(binary_image = png_bytes).execute()
