from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.social_cards.domain import (
    SocialAuthor,
    SocialLinkPreview,
    SocialMediaItem,
    SocialMediaKind,
    SocialPlatformBrand,
    SocialPost,
)
from features.web_browsing.twitter_status_fetcher import TweetData, TweetLinkPreview, TweetMediaItem
from features.web_browsing.twitter_utils import resolve_tweet_id
from util import log
from util.error_codes import WEB_FETCH_FAILED
from util.errors import ValidationError

TWITTER_PLATFORM = SocialPlatformBrand(
    platform_id = "x",
    display_name = "X",
    logo_light_key = "x_logo_light",
    logo_dark_key = "x_logo_dark",
)


class TwitterSocialPostProvider:

    tool_type = ToolType.api_twitter

    __di: DI
    __api_tool: ConfiguredTool
    __vision_tool: ConfiguredTool

    def __init__(self, di: DI, api_tool: ConfiguredTool, vision_tool: ConfiguredTool):
        self.__di = di
        self.__api_tool = api_tool
        self.__vision_tool = vision_tool

    @staticmethod
    def can_handle(url: str) -> bool:
        return resolve_tweet_id(url) is not None

    def fetch(self, url: str) -> SocialPost:
        tweet_id = resolve_tweet_id(url)
        if not tweet_id:
            raise ValidationError(f"Cannot resolve tweet ID from URL: {url}", WEB_FETCH_FAILED)
        return self.__fetch_tweet(tweet_id, url, include_embedded = True)

    def __fetch_tweet(
        self,
        tweet_id: str,
        source_url: str | None,
        include_embedded: bool,
    ) -> SocialPost:
        fetcher = self.__di.twitter_status_fetcher(tweet_id, self.__api_tool, self.__vision_tool)
        tweet = fetcher.as_structured()
        embedded_post = self.__fetch_embedded_post(tweet) if include_embedded else None
        return self.__map_tweet(tweet, tweet_id, source_url, embedded_post)

    def __fetch_embedded_post(
        self,
        tweet: TweetData,
    ) -> SocialPost | None:
        referenced_id = tweet.quoted_tweet_id or tweet.replied_to_tweet_id
        if not referenced_id:
            return None
        try:
            return self.__fetch_tweet(referenced_id, None, include_embedded = False)
        except Exception as e:
            log.w(f"Failed to fetch referenced tweet {referenced_id}", e)
            return None

    def __map_tweet(
        self,
        tweet: TweetData,
        tweet_id: str,
        source_url: str | None,
        embedded_post: SocialPost | None,
    ) -> SocialPost:
        return SocialPost(
            platform = TWITTER_PLATFORM,
            author = SocialAuthor(
                display_name = tweet.user.name,
                handle = tweet.user.handle,
                avatar_url = self.__large_profile_image_url(tweet.user.profile_image_url),
                bio = tweet.user.bio,
            ),
            text = tweet.text,
            source_url = source_url or self.__source_url(tweet_id, tweet),
            language = tweet.language,
            created_at = tweet.created_at,
            media = [self.__map_media_item(media) for media in tweet.media],
            link_previews = [self.__map_link_preview(link_preview) for link_preview in tweet.link_previews],
            embedded_post = embedded_post,
        )

    @staticmethod
    def __map_media_item(media: TweetMediaItem) -> SocialMediaItem:
        return SocialMediaItem(
            kind = TwitterSocialPostProvider.__media_kind(media.media_type),
            url = media.url,
            preview_url = media.preview_url,
        )

    @staticmethod
    def __map_link_preview(link_preview: TweetLinkPreview) -> SocialLinkPreview:
        return SocialLinkPreview(
            expanded_url = link_preview.expanded_url,
            domain = link_preview.domain,
            title = link_preview.title,
            description = link_preview.description,
            image_url = link_preview.og_image_url,
        )

    @staticmethod
    def __media_kind(media_type: str) -> SocialMediaKind:
        if media_type == "photo":
            return SocialMediaKind.IMAGE
        if media_type == "animated_gif":
            return SocialMediaKind.GIF
        if media_type == "video":
            return SocialMediaKind.VIDEO
        return SocialMediaKind.UNKNOWN

    @staticmethod
    def __large_profile_image_url(profile_image_url: str | None) -> str | None:
        if not profile_image_url:
            return None
        return profile_image_url.replace("_normal", "_bigger")

    @staticmethod
    def __source_url(tweet_id: str, tweet: TweetData) -> str:
        return f"https://x.com/{tweet.user.handle}/status/{tweet_id}"
