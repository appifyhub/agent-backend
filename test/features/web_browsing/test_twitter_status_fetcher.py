import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import requests
import requests_mock
from pydantic import SecretStr
from requests_mock import Mocker

from di.di import DI
from features.external_tools.tool_choice_resolver import ConfiguredTool
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from features.web_browsing.twitter_status_fetcher import (
    TweetData,
    TweetLinkPreview,
    TweetMediaItem,
    TweetMediaVariant,
    TwitterStatusFetcher,
)
from util.config import config


class TwitterStatusFetcherTest(unittest.TestCase):

    tweet_id: str
    api_url: str
    cache_entry: ToolsCache
    mock_di: DI
    mock_x_api_tool: ConfiguredTool
    mock_vision_tool: ConfiguredTool

    def setUp(self):
        config.web_timeout_s = 0
        self.tweet_id = "123456789"
        self.api_url = f"https://api.x.com/2/tweets/{self.tweet_id}"
        self.cache_entry = ToolsCache(
            key = "twitter-status-fetcher::123456789",
            value = "This is cached tweet content",
            expires_at = datetime.now() + timedelta(minutes = 5),
        )

        # Set up DI container
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.tools_cache_repo = MagicMock(spec = ToolsCacheRepository)
        self.mock_di.tools_cache_repo.save.return_value = None
        self.mock_di.computer_vision_analyzer = MagicMock()

        # Mock invoker and chat for usage tracking
        mock_user = Mock()
        mock_user.id = UUID(int = 1)
        self.mock_di.invoker = mock_user

        mock_chat = Mock()
        mock_chat.chat_id = UUID(int = 2)
        self.mock_di.require_invoker_chat = MagicMock(return_value = mock_chat)

        # Mock tracked_http_get to return a mock that delegates to requests.get
        mock_http_client = MagicMock()
        mock_http_client.get = requests.get
        self.mock_di.tracked_http_get = MagicMock(return_value = mock_http_client)

        # Set up configured tools
        mock_x_tool = MagicMock()
        mock_x_tool.id = "x.api-v2-post.read"
        self.mock_x_api_tool = ConfiguredTool(
            definition = mock_x_tool,
            token = SecretStr("test_x_bearer_token"),
            purpose = MagicMock(),
            payer_id = UUID(int = 1),
            uses_credits = False,
        )

        mock_vision_tool = MagicMock()
        mock_vision_tool.id = "vision-tool-id"
        self.mock_vision_tool = ConfiguredTool(
            definition = mock_vision_tool,
            token = SecretStr("test_vision_token"),
            purpose = MagicMock(),
            payer_id = UUID(int = 1),
            uses_credits = False,
        )

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_execute_cache_hit(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_repo.get.return_value = self.cache_entry

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.execute()
        self.assertEqual(result, "This is cached tweet content")

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_execute_expired_cache_refreshes(self, m: Mocker, mock_sleep):
        expired = ToolsCache(
            key = "expired",
            value = "Expired tweet content",
            expires_at = datetime.now() - timedelta(seconds = 1),
        )
        self.mock_di.tools_cache_repo.get.side_effect = [expired, None]
        m.get(
            self.api_url,
            json = {
                "data": {"text": "Fresh tweet content", "lang": "en"},
                "includes": {"users": [{"username": "testuser", "name": "Test User"}]},
            },
        )

        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.execute()

        self.assertIn("Fresh tweet content", result)
        self.assertEqual(self.mock_di.tools_cache_repo.save.call_count, 2)

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_execute_cache_miss(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_repo.get.return_value = None

        # Mock the X API v2 response
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Test tweet content",
                    "lang": "en",
                    "author_id": "123",
                },
                "includes": {
                    "users": [
                        {
                            "id": "123",
                            "username": "testuser",
                            "name": "Test User",
                            "description": "Test bio",
                        },
                    ],
                },
            },
        )

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.execute()
        self.assertIn("@testuser (Test User)", result)
        self.assertIn("Test tweet content", result)
        self.assertIn("@testuser's bio:", result)

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_execute_api_error(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_repo.get.return_value = None

        # Mock API error response
        m.get(self.api_url, status_code = 500)

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        with self.assertRaises(requests.exceptions.HTTPError):
            fetcher.execute()

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_api_call_parameters(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_repo.get.return_value = None

        # Mock the X API v2 response
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Test tweet content",
                    "lang": "en",
                    "author_id": "123",
                },
                "includes": {
                    "users": [
                        {
                            "id": "123",
                            "username": "testuser",
                            "name": "Test User",
                            "description": "Test bio",
                        },
                    ],
                },
            },
        )

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        fetcher.execute()

        # Verify API was called with correct parameters
        self.assertEqual(len(m.request_history), 1)
        request = m.request_history[0]
        self.assertEqual(request.method, "GET")
        self.assertIn("123456789", request.url)
        self.assertIn("Bearer test_x_bearer_token", request.headers.get("Authorization", ""))
        self.assertEqual(
            set(request.qs["media.fields"][0].split(",")),
            {"url", "type", "preview_image_url", "variants", "duration_ms", "width", "height", "alt_text"},
        )

    # noinspection PyUnusedLocal
    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_resolve_photo_contents(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_repo.get.return_value = None

        # Mock computer vision analyzer
        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.execute.return_value = "Photo description"
        self.mock_di.computer_vision_analyzer.return_value = mock_analyzer_instance

        # Mock the X API v2 response with photo
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Test tweet content",
                    "lang": "en",
                    "author_id": "123",
                    "attachments": {
                        "media_keys": ["3_123"],
                    },
                },
                "includes": {
                    "users": [
                        {
                            "id": "123",
                            "username": "testuser",
                            "name": "Test User",
                            "description": "Test bio",
                        },
                    ],
                    "media": [
                        {
                            "media_key": "3_123",
                            "type": "photo",
                            "url": "https://example.com/photo.jpg",
                        },
                    ],
                },
            },
        )

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.execute()

        self.assertIn("Photo description", result)
        # noinspection PyUnresolvedReferences
        self.mock_di.computer_vision_analyzer.assert_called_once()
        self.assertEqual(self.mock_di.computer_vision_analyzer.call_args.kwargs["image_mime_type"], "image/jpeg")

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_format_tweet_content_handles_missing_data(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None

        # Mock X API v2 response with missing data
        m.get(
            self.api_url,
            json = {
                "data": {
                    "lang": "en",
                    "author_id": "123",
                },
                "includes": {
                    "users": [
                        {
                            "id": "123",
                            "username": "testuser",
                        },
                    ],
                },
            },
        )

        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.execute()

        # Should handle missing data gracefully
        self.assertIn("@testuser (<Anonymous>)", result)
        self.assertIn("@testuser's bio: \"<No user bio>\"", result)
        self.assertIn("<No text posted>", result)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_returns_typed_data(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Structured tweet text",
                    "lang": "en",
                    "created_at": "2026-05-04T14:13:00.000Z",
                    "author_id": "123",
                },
                "includes": {
                    "users": [
                        {
                            "id": "123",
                            "username": "structuser",
                            "name": "Structured User",
                            "description": "A bio",
                            "profile_image_url": "https://pbs.twimg.com/profile_images/1/photo_normal.jpg",
                        },
                    ],
                    "media": [
                        {
                            "type": "photo",
                            "url": "https://pbs.twimg.com/media/photo.jpg",
                            "preview_image_url": None,
                        },
                        {
                            "type": "animated_gif",
                            "url": None,
                            "preview_image_url": "https://pbs.twimg.com/media/gif_preview.jpg",
                            "variants": [
                                {
                                    "url": "https://video.twimg.com/gif.mp4",
                                    "content_type": "video/mp4",
                                },
                            ],
                            "width": 640,
                            "height": 360,
                        },
                        {
                            "type": "video",
                            "url": None,
                            "preview_image_url": "https://pbs.twimg.com/media/video_preview.jpg",
                            "variants": [
                                {
                                    "url": "https://video.twimg.com/video-low.mp4",
                                    "content_type": "video/mp4",
                                    "bit_rate": 256000,
                                },
                            ],
                            "duration_ms": 12345,
                            "width": 1920,
                            "height": 1080,
                            "alt_text": "A test video",
                        },
                    ],
                },
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

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

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_parses_cached_media_variants(self, m: Mocker, _):
        raw_cache_key = ToolsCache.create_key("twitter-status-fetcher-json", self.tweet_id)
        self.mock_di.tools_cache_repo.get.return_value = ToolsCache(
            key = raw_cache_key,
            value = json.dumps({
                "data": {"text": "Cached video"},
                "includes": {
                    "users": [{"username": "cached"}],
                    "media": [
                        {
                            "type": "video",
                            "preview_image_url": "https://pbs.twimg.com/media/preview.jpg",
                            "variants": [
                                {
                                    "url": "https://video.twimg.com/cached.mp4",
                                    "content_type": "video/mp4",
                                    "bit_rate": 512000,
                                },
                            ],
                        },
                    ],
                },
            }),
            expires_at = datetime.now() + timedelta(minutes = 5),
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )

        result = fetcher.as_structured()

        self.assertEqual(result.media[0].variants[0].url, "https://video.twimg.com/cached.mp4")
        self.assertEqual(len(m.request_history), 0)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_uses_structured_cache_prefix(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {"data": {"text": "Test", "lang": "en"}, "includes": {"users": [{"username": "u"}]}},
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        fetcher.as_structured()

        expected_key = ToolsCache.create_key("twitter-status-fetcher-json", self.tweet_id)
        self.mock_di.tools_cache_repo.get.assert_called_once_with(expected_key)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_does_not_invoke_cv(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {"text": "Tweet", "lang": "en"},
                "includes": {
                    "users": [{"username": "u", "name": "U"}],
                    "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/photo.jpg"}],
                },
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = "123456789",
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        fetcher.as_structured()

        # noinspection PyUnresolvedReferences
        self.mock_di.computer_vision_analyzer.assert_not_called()

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_extracts_quoted_tweet_id(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Check this out https://t.co/abc123",
                    "lang": "en",
                    "entities": {
                        "urls": [
                            {
                                "url": "https://t.co/abc123",
                                "expanded_url": "https://x.com/someone/status/9876543210",
                            },
                        ],
                    },
                },
                "includes": {"users": [{"username": "poster"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertEqual(result.quoted_tweet_id, "9876543210")
        self.assertNotIn("https://t.co/abc123", result.text)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_no_quoted_tweet_for_self_media(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "My photo https://t.co/xyz",
                    "lang": "en",
                    "entities": {
                        "urls": [
                            {
                                "url": "https://t.co/xyz",
                                "expanded_url": f"https://x.com/me/status/{self.tweet_id}/photo/1",
                            },
                        ],
                    },
                },
                "includes": {"users": [{"username": "me"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertIsNone(result.quoted_tweet_id)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_extracts_link_previews(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Read this https://t.co/link1",
                    "lang": "en",
                    "entities": {
                        "urls": [
                            {
                                "url": "https://t.co/link1",
                                "expanded_url": "https://www.example.com/article",
                                "title": "Great Article",
                                "description": "A deep dive",
                                "images": [{"url": "https://example.com/og.jpg"}],
                            },
                        ],
                    },
                },
                "includes": {"users": [{"username": "poster"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertEqual(len(result.link_previews), 1)
        lp = result.link_previews[0]
        self.assertIsInstance(lp, TweetLinkPreview)
        self.assertEqual(lp.title, "Great Article")
        self.assertEqual(lp.description, "A deep dive")
        self.assertEqual(lp.domain, "example.com")
        self.assertEqual(lp.og_image_url, "https://example.com/og.jpg")
        self.assertNotIn("https://t.co/link1", result.text)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_unescapes_html_entities(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "AT&amp;T &lt;3 Tom &amp; Jerry",
                    "lang": "en",
                },
                "includes": {"users": [{"username": "poster"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertEqual(result.text, "AT&T <3 Tom & Jerry")

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_referenced_tweets_quoted(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Quoting this",
                    "lang": "en",
                    "referenced_tweets": [{"type": "quoted", "id": "111222333"}],
                },
                "includes": {"users": [{"username": "quoter"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertEqual(result.quoted_tweet_id, "111222333")
        self.assertFalse(result.is_reply)
        self.assertIsNone(result.replied_to_tweet_id)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_referenced_tweets_reply(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Replying here",
                    "lang": "en",
                    "referenced_tweets": [{"type": "replied_to", "id": "444555666"}],
                },
                "includes": {"users": [{"username": "replier"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertTrue(result.is_reply)
        self.assertEqual(result.replied_to_tweet_id, "444555666")
        self.assertIsNone(result.quoted_tweet_id)

    @requests_mock.Mocker()
    @patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None)
    def test_as_structured_referenced_tweets_both(self, m: Mocker, _):
        self.mock_di.tools_cache_repo.get.return_value = None
        m.get(
            self.api_url,
            json = {
                "data": {
                    "text": "Reply with quote",
                    "lang": "en",
                    "referenced_tweets": [
                        {"type": "replied_to", "id": "444555666"},
                        {"type": "quoted", "id": "777888999"},
                    ],
                },
                "includes": {"users": [{"username": "both"}]},
            },
        )
        fetcher = TwitterStatusFetcher(
            tweet_id = self.tweet_id,
            x_api_tool = self.mock_x_api_tool,
            vision_tool = self.mock_vision_tool,
            di = self.mock_di,
        )
        result = fetcher.as_structured()

        self.assertTrue(result.is_reply)
        self.assertEqual(result.replied_to_tweet_id, "444555666")
        self.assertEqual(result.quoted_tweet_id, "777888999")
