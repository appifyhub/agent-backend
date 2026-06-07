import unittest
from unittest.mock import MagicMock, Mock, patch

from pydantic import SecretStr

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
from features.web_browsing.twitter_status_fetcher import TweetData, TweetMediaItem, TweetUserData
from util.error_codes import IMAGE_GENERATION_FAILED, WEB_FETCH_FAILED
from util.errors import ExternalServiceError, ValidationError


def _make_tweet(with_media: bool = False) -> TweetData:
    media = [
        TweetMediaItem(url = "https://pbs.twimg.com/media/abc.jpg", preview_url = None, media_type = "photo"),
    ] if with_media else []
    return TweetData(
        user = TweetUserData(
            name = "Test User",
            handle = "testuser",
            bio = None,
            profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
        ),
        text = "Hello world",
        language = "en",
        created_at = "2026-05-04T12:00:00Z",
        media = media,
    )


def _make_mock_di() -> DI:
    di = Mock(spec = DI)
    di.twitter_status_fetcher = MagicMock()
    di.url_shortener = MagicMock()
    di.image_uploader = MagicMock()
    return di


def _make_x_api_tool() -> ConfiguredTool:
    tool = MagicMock(spec = ConfiguredTool)
    tool.token = SecretStr("fake-bearer-token")
    return tool


class SocialCardOrchestratorTest(unittest.TestCase):

    mock_di: DI
    mock_x_api_tool: ConfiguredTool
    mock_vision_tool: ConfiguredTool

    def setUp(self):
        self.mock_di = _make_mock_di()
        self.mock_x_api_tool = _make_x_api_tool()
        self.mock_vision_tool = _make_x_api_tool()

    def _make_orchestrator(self) -> SocialCardOrchestrator:
        return SocialCardOrchestrator(self.mock_x_api_tool, self.mock_vision_tool, self.mock_di)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_happy_path_returns_image_url(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = b"profile-bytes"
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.return_value = "https://short.url/abc"
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.return_value = b"png-data"

        mock_uploader = MagicMock()
        mock_uploader.execute.return_value = "https://cdn.example.com/card.png"
        self.mock_di.image_uploader.return_value = mock_uploader

        result = self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(result, "https://cdn.example.com/card.png")
        mock_renderer.render.assert_called_once()

    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_invalid_url_raises_validation_error(self, mock_resolve):
        mock_resolve.return_value = None

        with self.assertRaises(ValidationError) as ctx:
            self._make_orchestrator().execute("https://example.com/not-a-tweet")

        self.assertEqual(ctx.exception.error_code, WEB_FETCH_FAILED)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_photo_download_failure_continues(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet(with_media = True)
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = None
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.return_value = "https://short.url/abc"
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.return_value = b"png-data"

        mock_uploader = MagicMock()
        mock_uploader.execute.return_value = "https://cdn.example.com/card.png"
        self.mock_di.image_uploader.return_value = mock_uploader

        result = self._make_orchestrator().execute("https://x.com/user/status/123456789")
        self.assertEqual(result, "https://cdn.example.com/card.png")

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_render_failure_raises_external_service_error(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = None
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.return_value = "https://short.url/abc"
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.side_effect = RuntimeError("SVG rendering blew up")

        with self.assertRaises(ExternalServiceError) as ctx:
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(ctx.exception.error_code, IMAGE_GENERATION_FAILED)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_upload_failure_propagates(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = None
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.return_value = "https://short.url/abc"
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.return_value = b"png-data"

        mock_uploader = MagicMock()
        mock_uploader.execute.side_effect = ExternalServiceError("imgbb is down", 5004)
        self.mock_di.image_uploader.return_value = mock_uploader

        with self.assertRaises(ExternalServiceError):
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_url_shortener_failure_falls_back_to_original(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = None
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.side_effect = ExternalServiceError("shortener down", 5005)
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.return_value = b"png-data"

        mock_uploader = MagicMock()
        mock_uploader.execute.return_value = "https://cdn.example.com/card.png"
        self.mock_di.image_uploader.return_value = mock_uploader

        original_url = "https://x.com/user/status/123456789"
        self._make_orchestrator().execute(original_url)

        _, kwargs = mock_renderer.render.call_args
        self.assertEqual(kwargs["short_url"], original_url)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    @patch("features.social_cards.social_card_orchestrator.PhotoDownloader")
    @patch("features.social_cards.social_card_orchestrator.resolve_tweet_id")
    def test_profile_url_transform_normal_to_bigger(self, mock_resolve, mock_downloader_cls, mock_renderer):
        mock_resolve.return_value = "123456789"
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher

        mock_downloader = MagicMock()
        mock_downloader.download.return_value = b"avatar"
        mock_downloader.download_many.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        mock_shortener = MagicMock()
        mock_shortener.execute.return_value = "https://short.url/abc"
        self.mock_di.url_shortener.return_value = mock_shortener

        mock_renderer.render.return_value = b"png-data"

        mock_uploader = MagicMock()
        mock_uploader.execute.return_value = "https://cdn.example.com/card.png"
        self.mock_di.image_uploader.return_value = mock_uploader

        self._make_orchestrator().execute("https://x.com/user/status/123456789")

        call_args = mock_downloader.download.call_args[0][0]
        self.assertIn("_bigger", call_args)
        self.assertNotIn("_normal", call_args)
