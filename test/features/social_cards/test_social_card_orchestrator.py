import unittest
from unittest.mock import MagicMock, Mock, patch

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.social_cards.domain import (
    SocialAuthor,
    SocialMediaItem,
    SocialMediaKind,
    SocialPlatformBrand,
    SocialPost,
)
from features.social_cards.providers.twitter_social_post_provider import TwitterSocialPostProvider
from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
from features.web_browsing.twitter_status_fetcher import TweetData, TweetUserData
from util.error_codes import IMAGE_GENERATION_FAILED, WEB_FETCH_FAILED
from util.errors import ExternalServiceError, ValidationError


def _make_post(with_media: bool = False) -> SocialPost:
    media = [
        SocialMediaItem(
            kind = SocialMediaKind.IMAGE,
            url = "https://pbs.twimg.com/media/abc.jpg",
        ),
    ] if with_media else []
    return SocialPost(
        platform = SocialPlatformBrand(
            platform_id = "x",
            display_name = "X",
            logo_light_key = "x_logo_light",
            logo_dark_key = "x_logo_dark",
        ),
        author = SocialAuthor(
            display_name = "Test User",
            handle = "testuser",
        ),
        text = "Hello world",
        source_url = "https://x.com/user/status/123456789",
        language = "en",
        created_at = "2026-05-04T12:00:00Z",
        media = media,
    )


def _make_tweet() -> TweetData:
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
    )


def _make_mock_di() -> DI:
    di = Mock(spec = DI)
    di.url_shortener = MagicMock()
    di.require_invoker_chat.return_value = MagicMock(chat_id = "chat-1")
    di.invoker = MagicMock(id = "user-1")
    di.chat_attachment_service = MagicMock()
    di.chat_attachment_service.save.return_value = MagicMock(id = "att-1")
    di.chat_attachment_service.create_public_url.return_value = MagicMock(
        url = "https://cdn.example.com/card.png",
    )
    return di


def _make_tool(purpose: ToolType) -> ConfiguredTool:
    tool = MagicMock(spec = ConfiguredTool)
    tool.purpose = purpose
    return tool


class SocialCardOrchestratorTest(unittest.TestCase):

    mock_di: DI
    mock_x_api_tool: ConfiguredTool
    mock_vision_tool: ConfiguredTool
    mock_provider: MagicMock
    mock_downloader: MagicMock

    def setUp(self):
        self.mock_di = _make_mock_di()
        self.mock_x_api_tool = _make_tool(ToolType.api_twitter)
        self.mock_vision_tool = _make_tool(ToolType.vision)
        self.mock_provider = MagicMock()
        self.mock_provider.fetch.return_value = _make_post()
        self.mock_downloader = MagicMock()
        self.mock_downloader.download.return_value = None
        self.mock_di.social_post_provider_classes.return_value = [TwitterSocialPostProvider]
        self.mock_di.social_post_provider.return_value = self.mock_provider
        self.mock_di.photo_downloader.return_value = self.mock_downloader
        self.mock_di.url_shortener.return_value.execute.return_value = "https://short.url/abc"

    def _make_orchestrator(self) -> SocialCardOrchestrator:
        return SocialCardOrchestrator([self.mock_x_api_tool], self.mock_vision_tool, self.mock_di)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_happy_path_returns_image_url(self, mock_renderer):
        mock_renderer.render.return_value = b"png-data"
        url = "https://x.com/user/status/123456789"

        result = self._make_orchestrator().execute(url)

        self.assertEqual(result, "https://cdn.example.com/card.png")
        self.mock_provider.fetch.assert_called_once_with(url)
        self.mock_di.social_post_provider.assert_called_once_with(
            TwitterSocialPostProvider,
            self.mock_x_api_tool,
            self.mock_vision_tool,
        )
        mock_renderer.render.assert_called_once()
        self.mock_di.chat_attachment_service.save.assert_called_once()

    def test_invalid_url_raises_validation_error(self):
        with self.assertRaises(ValidationError) as ctx:
            self._make_orchestrator().execute("https://example.com/not-a-tweet")

        self.assertEqual(ctx.exception.error_code, WEB_FETCH_FAILED)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_photo_download_failure_continues(self, mock_renderer):
        self.mock_provider.fetch.return_value = _make_post(with_media = True)
        mock_renderer.render.return_value = b"png-data"

        result = self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(result, "https://cdn.example.com/card.png")
        self.mock_downloader.download.assert_called_once_with("https://pbs.twimg.com/media/abc.jpg")
        assets = mock_renderer.render.call_args.kwargs["assets"]
        self.assertEqual(assets.media, [])

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_render_failure_raises_external_service_error(self, mock_renderer):
        mock_renderer.render.side_effect = RuntimeError("SVG rendering blew up")

        with self.assertRaises(ExternalServiceError) as ctx:
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(ctx.exception.error_code, IMAGE_GENERATION_FAILED)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_upload_failure_propagates(self, mock_renderer):
        mock_renderer.render.return_value = b"png-data"
        self.mock_di.chat_attachment_service.save.side_effect = ExternalServiceError("storage is down", 5004)

        with self.assertRaises(ExternalServiceError):
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_url_shortener_failure_falls_back_to_original(self, mock_renderer):
        self.mock_di.url_shortener.return_value.execute.side_effect = ExternalServiceError("shortener down", 5005)
        mock_renderer.render.return_value = b"png-data"
        original_url = "https://x.com/user/status/123456789"

        self._make_orchestrator().execute(original_url)

        self.assertEqual(mock_renderer.render.call_args.kwargs["short_url"], original_url)

    def test_twitter_provider_transforms_profile_url_normal_to_bigger(self):
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertIn("_bigger", post.author.avatar_url)
        self.assertNotIn("_normal", post.author.avatar_url)
