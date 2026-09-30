from datetime import datetime, timedelta
from json import dumps, loads
from typing import cast
from unittest import TestCase
from unittest.mock import patch

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from requests.exceptions import HTTPError
from stubs import domain, external
from util.di_utils import di_for_tests

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_5, X_READ_POST
from features.tools_cache.tools_cache import ToolsCache
from features.web_browsing.twitter_status_fetcher import (
    CACHE_PREFIX,
    CACHE_PREFIX_STRUCTURED,
    CACHE_TTL,
    TweetData,
    TweetLinkPreview,
    TweetMediaItem,
    TweetMediaVariant,
    TwitterStatusFetcher,
)
from util.config import config


class TwitterStatusFetcherTest(TestCase):

    di: DI
    tweet_id: str
    api_url: str
    x_api_tool: ConfiguredTool
    http: FakeHTTPClient
    model: FakeChatModel
    fetcher: TwitterStatusFetcher

    def setUp(self):
        self.tweet_id = "123456789"
        self.api_url = f"https://api.x.com/2/tweets/{self.tweet_id}"
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.di.inject_invoker_chat(domain.chat_config())
        self.x_api_tool = domain.configured_tool(definition = X_READ_POST, purpose = ToolType.api_twitter)
        vision_tool = domain.configured_tool(definition = GPT_5_5, purpose = ToolType.vision)
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(vision_tool, max_tokens = 500))
        self.fetcher = self.di.twitter_status_fetcher(self.tweet_id, self.x_api_tool, vision_tool)
        # skip the system sleep used to space real API requests
        self.enterContext(patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None))

    def test_execute_cache_hit(self):
        cached = self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, self.tweet_id),
            value = "This is cached tweet content",
        ))

        result = self.fetcher.execute()

        self.assertEqual(result, cached.value)
        self.assertEqual(self.di.tools_cache_repo.get(cached.key), cached)
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.model.prompts, [])

    def test_execute_expired_cache_refreshes(self):
        expired = self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, self.tweet_id),
            expires_at = datetime.now() - timedelta(seconds = 1),
        ))
        payload = external.x_tweet_response(data = {"text": "Fresh tweet content", "lang": "en"})
        self.http.responses[self.api_url].append(external.http_json_response(payload))

        result = self.fetcher.execute()

        self.assertIn("Fresh tweet content", result)
        refreshed = self.di.tools_cache_repo.get(expired.key)
        self.assertEqual(refreshed.value, result)
        self.assertFalse(refreshed.is_expired())
        raw = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.tweet_id))
        self.assertEqual(loads(raw.value), payload)

    def test_execute_cache_miss(self):
        payload = external.x_tweet_response()
        self.http.responses[self.api_url].append(external.http_json_response(payload))
        started_at = datetime.now()

        result = self.fetcher.execute()

        self.assertIn("@testuser (Test User)", result)
        self.assertIn("Test tweet content", result)
        self.assertIn("@testuser's bio:", result)
        text_cache = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, self.tweet_id))
        raw_cache = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.tweet_id))
        self.assertEqual(text_cache.value, result)
        self.assertEqual(loads(raw_cache.value), payload)
        for cached in (text_cache, raw_cache):
            self.assertGreaterEqual(cached.expires_at, started_at + CACHE_TTL)
            self.assertLessEqual(cached.expires_at, datetime.now() + CACHE_TTL)

    def test_execute_api_error(self):
        self.http.responses[self.api_url].append(external.http_response(status_code = 500))

        with self.assertRaises(HTTPError) as raised:
            self.fetcher.execute()

        self.assertEqual(raised.exception.response.status_code, 500)
        self.assertIsNone(self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, self.tweet_id)))
        self.assertIsNone(self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.tweet_id)))

    def test_api_call_parameters(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response()))

        self.fetcher.execute()

        url, options = self.http.requests[0]
        self.assertEqual(len(self.http.requests), 1)
        self.assertEqual(url, self.api_url)
        self.assertEqual(options["headers"]["Authorization"], f"Bearer {self.x_api_tool.token.get_secret_value()}")
        self.assertEqual(options["timeout"], config.web_timeout_s)
        self.assertEqual(
            set(options["params"]["media.fields"].split(",")),
            {"url", "type", "preview_image_url", "variants", "duration_ms", "width", "height", "alt_text"},
        )

    def test_resolve_photo_contents(self):
        self.model.responses.append(external.ai_message(content = "Photo description"))
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            includes = {"media": [{"type": "photo", "url": "https://example.com/photo.jpg"}]},
        )))

        result = self.fetcher.execute()

        self.assertIn("Photo [1]: https://example.com/photo.jpg\nPhoto description", result)

    def test_format_tweet_content_handles_missing_data(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {"lang": "en", "author_id": "123"},
            includes = {"users": [{"id": "123", "username": "testuser"}]},
        )))

        result = self.fetcher.execute()

        self.assertIn("@testuser (<Anonymous>)", result)
        self.assertIn("@testuser's bio: \"<No user bio>\"", result)
        self.assertIn("<No text posted>", result)

    def test_as_structured_returns_typed_data(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Structured tweet text",
                "lang": "en",
                "created_at": "2026-05-04T14:13:00.000Z",
                "author_id": "123",
            },
            includes = {
                "users": [{
                    "id": "123",
                    "username": "structuser",
                    "name": "Structured User",
                    "description": "A bio",
                    "profile_image_url": "https://pbs.twimg.com/profile_images/1/photo_normal.jpg",
                }],
                "media": [
                    {"type": "photo", "url": "https://pbs.twimg.com/media/photo.jpg"},
                    {
                        "type": "animated_gif",
                        "preview_image_url": "https://pbs.twimg.com/media/gif_preview.jpg",
                        "variants": [{"url": "https://video.twimg.com/gif.mp4", "content_type": "video/mp4"}],
                        "width": 640,
                        "height": 360,
                    },
                    {
                        "type": "video",
                        "preview_image_url": "https://pbs.twimg.com/media/video_preview.jpg",
                        "variants": [{
                            "url": "https://video.twimg.com/video-low.mp4",
                            "content_type": "video/mp4",
                            "bit_rate": 256000,
                        }],
                        "duration_ms": 12345,
                        "width": 1920,
                        "height": 1080,
                        "alt_text": "A test video",
                    },
                ],
            },
        )))

        result = self.fetcher.as_structured()

        self.assertIsInstance(result, TweetData)
        self.assertEqual(result.user.handle, "structuser")
        self.assertEqual(result.user.name, "Structured User")
        self.assertEqual(result.user.bio, "A bio")
        self.assertIn("_normal", result.user.profile_image_url)
        self.assertEqual(result.text, "Structured tweet text")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.created_at, "2026-05-04T14:13:00.000Z")
        self.assertEqual(len(result.media), 3)
        self.assertIsInstance(result.media[0], TweetMediaItem)
        self.assertEqual(result.media[0].media_type, "photo")
        self.assertEqual(result.media[0].url, "https://pbs.twimg.com/media/photo.jpg")
        self.assertEqual(result.media[1].media_type, "animated_gif")
        self.assertEqual(result.media[1].preview_url, "https://pbs.twimg.com/media/gif_preview.jpg")
        self.assertIsInstance(result.media[1].variants[0], TweetMediaVariant)
        self.assertEqual(result.media[1].variants[0].url, "https://video.twimg.com/gif.mp4")
        self.assertEqual(result.media[1].width, 640)
        self.assertEqual(result.media[1].height, 360)
        self.assertEqual(result.media[2].media_type, "video")
        self.assertEqual(result.media[2].preview_url, "https://pbs.twimg.com/media/video_preview.jpg")
        self.assertEqual(result.media[2].variants[0].bit_rate, 256000)
        self.assertEqual(result.media[2].duration_ms, 12345)
        self.assertEqual(result.media[2].width, 1920)
        self.assertEqual(result.media[2].height, 1080)
        self.assertEqual(result.media[2].alt_text, "A test video")

    def test_as_structured_parses_cached_media_variants(self):
        payload = external.x_tweet_response(
            data = {"text": "Cached video"},
            includes = {
                "users": [{"username": "cached"}],
                "media": [{
                    "type": "video",
                    "preview_image_url": "https://pbs.twimg.com/media/preview.jpg",
                    "variants": [{
                        "url": "https://video.twimg.com/cached.mp4",
                        "content_type": "video/mp4",
                        "bit_rate": 512000,
                    }],
                }],
            },
        )
        self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.tweet_id),
            value = dumps(payload),
        ))

        result = self.fetcher.as_structured()

        self.assertEqual(result.media[0].variants[0].url, "https://video.twimg.com/cached.mp4")
        self.assertEqual(self.http.requests, [])

    def test_as_structured_uses_structured_cache_prefix(self):
        text_cache = self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, self.tweet_id),
            value = "Rendered tweet text",
        ))
        payload = external.x_tweet_response()
        self.http.responses[self.api_url].append(external.http_json_response(payload))

        result = self.fetcher.as_structured()

        self.assertEqual(result.text, payload["data"]["text"])
        raw_cache = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX_STRUCTURED, self.tweet_id))
        self.assertEqual(loads(raw_cache.value), payload)
        self.assertEqual(self.di.tools_cache_repo.get(text_cache.key), text_cache)

    def test_as_structured_does_not_invoke_cv(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            includes = {"media": [{"type": "photo", "url": "https://pbs.twimg.com/media/photo.jpg"}]},
        )))

        result = self.fetcher.as_structured()

        self.assertEqual(result.media[0].url, "https://pbs.twimg.com/media/photo.jpg")
        self.assertEqual(self.model.prompts, [])

    def test_as_structured_extracts_quoted_tweet_id(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Check this out https://t.co/abc123",
                "entities": {"urls": [{
                    "url": "https://t.co/abc123",
                    "expanded_url": "https://x.com/someone/status/9876543210",
                }]},
            },
        )))

        result = self.fetcher.as_structured()

        self.assertEqual(result.quoted_tweet_id, "9876543210")
        self.assertNotIn("https://t.co/abc123", result.text)

    def test_as_structured_no_quoted_tweet_for_self_media(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "My photo https://t.co/xyz",
                "entities": {"urls": [{
                    "url": "https://t.co/xyz",
                    "expanded_url": f"https://x.com/me/status/{self.tweet_id}/photo/1",
                }]},
            },
        )))

        result = self.fetcher.as_structured()

        self.assertIsNone(result.quoted_tweet_id)

    def test_as_structured_extracts_link_previews(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Read this https://t.co/link1",
                "entities": {"urls": [{
                    "url": "https://t.co/link1",
                    "expanded_url": "https://www.example.com/article",
                    "title": "Great Article",
                    "description": "A deep dive",
                    "images": [{"url": "https://example.com/og.jpg"}],
                }]},
            },
        )))

        result = self.fetcher.as_structured()

        self.assertEqual(len(result.link_previews), 1)
        preview = result.link_previews[0]
        self.assertIsInstance(preview, TweetLinkPreview)
        self.assertEqual(preview.title, "Great Article")
        self.assertEqual(preview.description, "A deep dive")
        self.assertEqual(preview.domain, "example.com")
        self.assertEqual(preview.og_image_url, "https://example.com/og.jpg")
        self.assertNotIn("https://t.co/link1", result.text)

    def test_as_structured_unescapes_html_entities(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {"text": "AT&amp;T &lt;3 Tom &amp; Jerry"},
        )))

        result = self.fetcher.as_structured()

        self.assertEqual(result.text, "AT&T <3 Tom & Jerry")

    def test_as_structured_referenced_tweets_quoted(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Quoting this",
                "referenced_tweets": [{"type": "quoted", "id": "111222333"}],
            },
        )))

        result = self.fetcher.as_structured()

        self.assertEqual(result.quoted_tweet_id, "111222333")
        self.assertFalse(result.is_reply)
        self.assertIsNone(result.replied_to_tweet_id)

    def test_as_structured_referenced_tweets_reply(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Replying here",
                "referenced_tweets": [{"type": "replied_to", "id": "444555666"}],
            },
        )))

        result = self.fetcher.as_structured()

        self.assertTrue(result.is_reply)
        self.assertEqual(result.replied_to_tweet_id, "444555666")
        self.assertIsNone(result.quoted_tweet_id)

    def test_as_structured_referenced_tweets_both(self):
        self.http.responses[self.api_url].append(external.http_json_response(external.x_tweet_response(
            data = {
                "text": "Reply with quote",
                "referenced_tweets": [
                    {"type": "replied_to", "id": "444555666"},
                    {"type": "quoted", "id": "777888999"},
                ],
            },
        )))

        result = self.fetcher.as_structured()

        self.assertTrue(result.is_reply)
        self.assertEqual(result.replied_to_tweet_id, "444555666")
        self.assertEqual(result.quoted_tweet_id, "777888999")
