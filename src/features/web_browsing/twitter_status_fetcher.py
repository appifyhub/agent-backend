import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import sleep
from typing import Any
from urllib.parse import urlparse

from di.di import DI
from features.accounting.usage.decorators.http_usage_tracking_decorator import HTTPUsageTrackingDecorator
from features.chat.supported_files import KNOWN_IMAGE_FORMATS
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.tools_cache.tools_cache import ToolsCache
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE
from util.errors import ExternalServiceError

CACHE_PREFIX = "twitter-status-fetcher"
CACHE_PREFIX_STRUCTURED = "twitter-status-fetcher-json"
CACHE_TTL = timedelta(weeks = 1)
RATE_LIMIT_DELAY_S = 2


@dataclass
class TweetLinkPreview:
    title: str | None
    description: str | None
    og_image_url: str | None
    expanded_url: str
    domain: str


@dataclass
class TweetMediaItem:
    url: str | None
    preview_url: str | None
    media_type: str  # "photo", "animated_gif", "video"


@dataclass
class TweetUserData:
    name: str | None
    handle: str
    bio: str | None
    profile_image_url: str | None


@dataclass
class TweetData:
    user: TweetUserData
    text: str
    language: str | None
    created_at: str | None
    media: list[TweetMediaItem] = field(default_factory = list)
    link_previews: list[TweetLinkPreview] = field(default_factory = list)
    quoted_tweet_id: str | None = None
    is_reply: bool = False
    replied_to_tweet_id: str | None = None


class TwitterStatusFetcher:

    TWITTER_TOOL_TYPE: ToolType = ToolType.api_twitter
    VISION_TOOL_TYPE: ToolType = ToolType.vision

    __tweet_id: str
    __x_api_tool: ConfiguredTool
    __vision_tool: ConfiguredTool
    __http_client: HTTPUsageTrackingDecorator
    __di: DI

    def __init__(
        self,
        tweet_id: str,
        x_api_tool: ConfiguredTool,
        vision_tool: ConfiguredTool,
        di: DI,
    ):
        self.__tweet_id = tweet_id
        self.__x_api_tool = x_api_tool
        self.__vision_tool = vision_tool
        self.__http_client = di.tracked_http_get(x_api_tool)
        self.__di = di

    def execute(self) -> str:
        return self.as_text()

    def as_text(self) -> str:
        log.t(f"Fetching text content for tweet ID: {self.__tweet_id}")
        text_cache_key = ToolsCache.create_key(CACHE_PREFIX, self.__tweet_id)
        cached = self.__get_cached_string(text_cache_key)
        if cached:
            return cached
        raw = self.__fetch_raw()
        resolved = self.__resolve_content(raw)
        self.__di.tools_cache_repo.save(
            ToolsCache(
                key = text_cache_key,
                value = resolved,
                expires_at = datetime.now() + CACHE_TTL,
            ),
        )
        log.t(f"Text cache updated for key '{text_cache_key}'")
        return resolved

    def as_structured(self) -> TweetData:
        log.t(f"Fetching structured data for tweet ID: {self.__tweet_id}")
        raw = self.__fetch_raw()
        return self.__parse_structured(raw)

    def __fetch_raw(self) -> dict[str, Any]:
        raw_cache_key = ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.__tweet_id)
        cached_json = self.__get_cached_string(raw_cache_key)
        if cached_json:
            return json.loads(cached_json)

        api_url = f"https://api.x.com/2/tweets/{self.__tweet_id}"
        headers = {
            "Authorization": f"Bearer {self.__x_api_tool.token.get_secret_value()}",
        }
        params = {
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "name,username,description,profile_image_url",
            "tweet.fields": "lang,text,created_at,note_tweet,entities,referenced_tweets",
            "media.fields": "url,type,preview_image_url",
        }

        sleep(RATE_LIMIT_DELAY_S)
        response = self.__http_client.get(api_url, headers = headers, params = params, timeout = config.web_timeout_s)
        response.raise_for_status()
        response_json = response.json() or {}

        self.__di.tools_cache_repo.save(
            ToolsCache(
                key = raw_cache_key,
                value = json.dumps(response_json),
                expires_at = datetime.now() + CACHE_TTL,
            ),
        )
        log.t(f"Raw cache updated for key '{raw_cache_key}'")
        return response_json

    def __get_cached_string(self, cache_key: str) -> str | None:
        log.t(f"Checking cache for key: '{cache_key}'")
        cache_entry = self.__di.tools_cache_repo.get(cache_key)
        if cache_entry:
            if not cache_entry.is_expired():
                log.t(f"Cache hit for key '{cache_key}'")
                return cache_entry.value
            log.t(f"Cache expired for key '{cache_key}'")
        log.t(f"Cache miss for key '{cache_key}'")
        return None

    def __parse_structured(self, response: dict[str, Any]) -> TweetData:
        post_data = response.get("data") or {}
        includes = response.get("includes") or {}

        users = includes.get("users") or []
        user_raw = users[0] if users else {}

        user = TweetUserData(
            name = user_raw.get("name") or None,
            handle = user_raw.get("username") or "unknown",
            bio = user_raw.get("description") or None,
            profile_image_url = user_raw.get("profile_image_url") or None,
        )

        media_items: list[TweetMediaItem] = []
        for m in includes.get("media") or []:
            media_type = m.get("type") or "photo"
            media_items.append(
                TweetMediaItem(
                    url = m.get("url") or None,
                    preview_url = m.get("preview_image_url") or None,
                    media_type = media_type,
                ),
            )

        note_tweet = post_data.get("note_tweet") or {}
        text = html.unescape(note_tweet.get("text") or post_data.get("text") or "<No text posted>")

        entities = note_tweet.get("entities") or post_data.get("entities") or {}
        entity_urls = entities.get("urls") or []

        referenced_tweets = post_data.get("referenced_tweets") or []
        quoted_tweet_id: str | None = None
        is_reply = False
        replied_to_tweet_id: str | None = None
        for ref in referenced_tweets:
            ref_type = ref.get("type")
            ref_id = ref.get("id")
            if ref_type == "quoted" and ref_id:
                quoted_tweet_id = ref_id
            elif ref_type == "replied_to" and ref_id:
                is_reply = True
                replied_to_tweet_id = ref_id

        link_previews, text, url_quoted_id = self.__process_urls(text, entity_urls)
        if not quoted_tweet_id and url_quoted_id:
            quoted_tweet_id = url_quoted_id

        return TweetData(
            user = user,
            text = text,
            language = post_data.get("lang") or None,
            created_at = post_data.get("created_at") or None,
            media = media_items,
            link_previews = link_previews,
            quoted_tweet_id = quoted_tweet_id,
            is_reply = is_reply,
            replied_to_tweet_id = replied_to_tweet_id,
        )

    def __process_urls(
        self,
        text: str,
        entity_urls: list[dict[str, Any]],
    ) -> tuple[list[TweetLinkPreview], str, str | None]:
        link_previews: list[TweetLinkPreview] = []
        tco_urls_to_strip: set[str] = set()
        quoted_tweet_id: str | None = None

        for entity in entity_urls:
            tco_url = entity.get("url") or ""
            expanded = entity.get("expanded_url") or ""

            if not tco_url:
                continue

            is_media_self_ref = f"/status/{self.__tweet_id}/" in expanded
            is_twitter_domain = any(
                d in expanded for d in ["x.com/", "twitter.com/"]
            )

            if is_media_self_ref:
                tco_urls_to_strip.add(tco_url)
            elif is_twitter_domain:
                qt_id = self.__extract_tweet_id_from_url(expanded)
                if qt_id:
                    quoted_tweet_id = qt_id
                    tco_urls_to_strip.add(tco_url)
            else:
                tco_urls_to_strip.add(tco_url)
                title = entity.get("title") or None
                description = entity.get("description") or None
                if title or description:
                    images = entity.get("images") or []
                    og_image_url = images[0].get("url") if images else None
                    parsed = urlparse(expanded)
                    domain = parsed.hostname or ""
                    if domain.startswith("www."):
                        domain = domain[4:]
                    parts = domain.split(".")
                    if len(parts) > 2:
                        domain = ".".join(parts[-2:])
                    link_previews.append(
                        TweetLinkPreview(
                            title = title,
                            description = description,
                            og_image_url = og_image_url,
                            expanded_url = expanded,
                            domain = domain,
                        ),
                    )

        for tco_url in tco_urls_to_strip:
            text = text.replace(tco_url, "")

        text = re.sub(r" +", " ", text).strip()
        return link_previews, text, quoted_tweet_id

    @staticmethod
    def __extract_tweet_id_from_url(url: str) -> str | None:
        parts = url.split("/status/")
        if len(parts) == 2:
            return parts[1].split("?")[0].split("/")[0]
        return None

    def __resolve_content(self, response: dict[str, Any]) -> str:
        try:
            post_data = response.get("data") or {}
            includes = response.get("includes") or {}

            post_language = post_data.get("lang") or "<No language given>"
            note_tweet = post_data.get("note_tweet") or {}
            post_text = note_tweet.get("text") or post_data.get("text") or "<No text posted>"

            users = includes.get("users") or []
            user = users[0] if users else {}
            name = user.get("name") or "<Anonymous>"
            username = user.get("username") or "anonymous"
            bio = user.get("description") or "<No user bio>"

            text_contents = "\n".join(
                [
                    f"A tweet-post by @{username} ({name}), language {post_language}:",
                    f"\n{post_text}\n",
                ],
            )
            photo_contents = self.__resolve_photo_contents(includes, text_contents)
            bio_contents = f"@{username}'s bio: \"{bio}\""

            sections = [text_contents]
            if photo_contents:
                sections.append("\n".join(photo_contents))
            sections.append(bio_contents)
            return "\n—\n".join(sections).strip()
        except Exception as e:
            raise ExternalServiceError("Error formatting tweet content", EXTERNAL_EMPTY_RESPONSE) from e

    def __resolve_photo_contents(self, includes: dict[str, Any], additional_context: str | None) -> list[str]:
        log.t(f"Resolving photo contents for tweet {self.__tweet_id}")
        media_list = includes.get("media") or []
        photo_descriptions: list[str] = []
        for i, media in enumerate(media_list):
            try:
                url = media.get("url") or None
                media_type = media.get("type") or None
                if url and media_type == "photo":
                    extension = url.lower().split(".")[-1]
                    mime_type = KNOWN_IMAGE_FORMATS.get(extension) if extension else KNOWN_IMAGE_FORMATS.get("png")
                    analyzer = self.__di.computer_vision_analyzer(
                        job_id = f"tweet-{self.__tweet_id}",
                        image_mime_type = str(mime_type),
                        configured_tool = self.__vision_tool,
                        image_url = url,
                        additional_context = f"[[ Tweet / X Post ]]\n\n{additional_context}",
                    )
                    description = analyzer.execute()
                    if description:
                        photo_descriptions.append(f"Photo [{i + 1}]: {url}\n{description}\n")
            except Exception as e:
                log.w(f"Error resolving photo {i + 1} from tweet {self.__tweet_id}", e)
        return photo_descriptions
