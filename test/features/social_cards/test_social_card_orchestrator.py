import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from PIL import Image

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.social_cards.domain import (
    SocialAuthor,
    SocialDynamicMedia,
    SocialMediaItem,
    SocialMediaKind,
    SocialPlatformBrand,
    SocialPost,
)
from features.social_cards.providers.twitter_social_post_provider import TwitterSocialPostProvider
from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
from features.web_browsing.photo_downloader import PhotoDownloader
from features.web_browsing.twitter_status_fetcher import TweetData, TweetMediaItem, TweetMediaVariant, TweetUserData
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


def _make_tweet(media: list[TweetMediaItem] | None = None) -> TweetData:
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
        media = media or [],
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


def _write_test_image(path: Path) -> None:
    Image.new("RGB", (32, 24), color = (100, 50, 25)).save(path)


def _render_to_path(**kwargs: object) -> None:
    Path(kwargs["output_path"]).write_bytes(b"png-data")


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
        self.mock_downloader.download_to.return_value = False
        self.mock_di.social_post_provider_classes.return_value = [TwitterSocialPostProvider]
        self.mock_di.social_post_provider.return_value = self.mock_provider
        self.mock_di.photo_downloader.return_value = self.mock_downloader
        self.mock_di.url_shortener.return_value.execute.return_value = "https://short.url/abc"

    def _make_orchestrator(self) -> SocialCardOrchestrator:
        return SocialCardOrchestrator([self.mock_x_api_tool], self.mock_vision_tool, self.mock_di)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_happy_path_returns_image_url(self, mock_renderer):
        mock_renderer.render.side_effect = _render_to_path
        url = "https://x.com/user/status/123456789"
        saved_paths: list[Path] = []

        def capture_save(**kwargs: object):
            saved_path = Path(kwargs["file_path"])
            self.assertTrue(saved_path.exists())
            saved_paths.append(saved_path)
            return MagicMock(id = "att-1")

        self.mock_di.chat_attachment_service.save.side_effect = capture_save

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
        self.assertFalse(saved_paths[0].exists())

    def test_invalid_url_raises_validation_error(self):
        with self.assertRaises(ValidationError) as ctx:
            self._make_orchestrator().execute("https://example.com/not-a-tweet")

        self.assertEqual(ctx.exception.error_code, WEB_FETCH_FAILED)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_photo_download_failure_continues(self, mock_renderer):
        self.mock_provider.fetch.return_value = _make_post(with_media = True)
        mock_renderer.render.side_effect = _render_to_path

        result = self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(result, "https://cdn.example.com/card.png")
        self.mock_downloader.download_to.assert_called_once()
        self.assertEqual(self.mock_downloader.download_to.call_args.args[0], "https://pbs.twimg.com/media/abc.jpg")
        assets = mock_renderer.render.call_args.kwargs["assets"]
        self.assertEqual(assets.media, [])

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_render_failure_raises_external_service_error(self, mock_renderer):
        output_paths: list[Path] = []

        def fail_render(**kwargs: object):
            output_paths.append(Path(kwargs["output_path"]))
            raise RuntimeError("SVG rendering blew up")

        mock_renderer.render.side_effect = fail_render

        with self.assertRaises(ExternalServiceError) as ctx:
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertEqual(ctx.exception.error_code, IMAGE_GENERATION_FAILED)
        self.assertFalse(output_paths[0].parent.exists())

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_upload_failure_propagates(self, mock_renderer):
        mock_renderer.render.side_effect = _render_to_path
        output_paths: list[Path] = []

        def fail_save(**kwargs: object):
            output_paths.append(Path(kwargs["file_path"]))
            raise ExternalServiceError("storage is down", 5004)

        self.mock_di.chat_attachment_service.save.side_effect = fail_save

        with self.assertRaises(ExternalServiceError):
            self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertFalse(output_paths[0].parent.exists())

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_url_shortener_failure_falls_back_to_original(self, mock_renderer):
        self.mock_di.url_shortener.return_value.execute.side_effect = ExternalServiceError("shortener down", 5005)
        mock_renderer.render.side_effect = _render_to_path
        original_url = "https://x.com/user/status/123456789"

        self._make_orchestrator().execute(original_url)

        self.assertEqual(mock_renderer.render.call_args.kwargs["short_url"], original_url)

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_recursive_assets_are_paths_cleaned_after_success(self, mock_renderer):
        embedded_media = SocialMediaItem(
            kind = SocialMediaKind.IMAGE,
            url = "https://example.com/embedded.jpg",
        )
        embedded = _make_post()
        embedded.author.avatar_url = "https://example.com/embedded-avatar.jpg"
        embedded.media = [embedded_media]
        post = _make_post(with_media = True)
        post.author.avatar_url = "https://example.com/avatar.jpg"
        post.embedded_post = embedded
        self.mock_provider.fetch.return_value = post

        def download_to(url: str, destination: Path) -> bool:
            _write_test_image(destination)
            return True

        self.mock_downloader.download_to.side_effect = download_to
        captured_paths: list[Path] = []

        def capture_render(**kwargs: object) -> None:
            assets = kwargs["assets"]
            captured_paths.extend([assets.avatar_path, assets.media[0].path])
            captured_paths.extend([assets.embedded_post.avatar_path, assets.embedded_post.media[0].path])
            self.assertTrue(all(path.exists() for path in captured_paths))
            _render_to_path(**kwargs)

        mock_renderer.render.side_effect = capture_render

        self._make_orchestrator().execute("https://x.com/user/status/123456789")

        self.assertTrue(captured_paths)
        self.assertTrue(all(not path.exists() for path in captured_paths))

    @patch("features.social_cards.social_card_orchestrator.card_renderer")
    def test_dynamic_media_downloads_poster_without_playback(self, mock_renderer):
        poster_url = "https://example.com/poster.jpg"
        playback_url = "https://example.com/video.mp4"
        post = _make_post()
        post.media = [
            SocialMediaItem(
                kind = SocialMediaKind.VIDEO,
                preview_url = poster_url,
                dynamic_media = SocialDynamicMedia(playback_url = playback_url),
            ),
        ]
        self.mock_provider.fetch.return_value = post

        def download_to(url: str, destination: Path) -> bool:
            _write_test_image(destination)
            return True

        self.mock_downloader.download_to.side_effect = download_to
        mock_renderer.render.side_effect = _render_to_path

        self._make_orchestrator().execute("https://x.com/user/status/123456789")

        downloaded_urls = [call.args[0] for call in self.mock_downloader.download_to.call_args_list]
        self.assertEqual(downloaded_urls, [poster_url])
        self.assertNotIn(playback_url, downloaded_urls)

    def test_twitter_provider_transforms_profile_url_normal_to_bigger(self):
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet()
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertIn("_bigger", post.author.avatar_url)
        self.assertNotIn("_normal", post.author.avatar_url)

    def test_twitter_provider_selects_highest_bitrate_mp4_video_variant(self):
        video = TweetMediaItem(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                TweetMediaVariant(
                    url = "https://video.twimg.com/video.m3u8",
                    content_type = "application/x-mpegURL",
                    bit_rate = 4000000,
                ),
                TweetMediaVariant(
                    url = "https://video.twimg.com/video-low.mp4",
                    content_type = "video/mp4",
                    bit_rate = 256000,
                ),
                TweetMediaVariant(
                    url = "https://video.twimg.com/video-high.mp4",
                    content_type = "video/mp4",
                    bit_rate = 1024000,
                ),
            ],
            duration_ms = 12345,
            width = 1920,
            height = 1080,
            alt_text = "A test video",
        )
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet([video])
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertEqual(len(post.media), 1)
        self.assertEqual(post.media[0].kind, SocialMediaKind.VIDEO)
        self.assertEqual(post.media[0].preview_url, video.preview_url)
        self.assertEqual(post.media[0].alt_text, "A test video")
        self.assertIsNotNone(post.media[0].dynamic_media)
        self.assertEqual(post.media[0].dynamic_media.playback_url, "https://video.twimg.com/video-high.mp4")
        self.assertEqual(post.media[0].dynamic_media.duration_seconds, 12.345)
        self.assertEqual(post.media[0].dynamic_media.width, 1920)
        self.assertEqual(post.media[0].dynamic_media.height, 1080)

    def test_twitter_provider_maps_animated_gif_variant_as_one_media_item(self):
        animated_gif = TweetMediaItem(
            url = None,
            preview_url = "https://pbs.twimg.com/media/gif-preview.jpg",
            media_type = "animated_gif",
            variants = [
                TweetMediaVariant(
                    url = "https://video.twimg.com/animation.mp4",
                    content_type = "video/mp4",
                    bit_rate = None,
                ),
            ],
        )
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet([animated_gif])
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertEqual(len(post.media), 1)
        self.assertEqual(post.media[0].kind, SocialMediaKind.GIF)
        self.assertEqual(post.media[0].preview_url, animated_gif.preview_url)
        self.assertEqual(post.media[0].dynamic_media.playback_url, "https://video.twimg.com/animation.mp4")

    def test_twitter_provider_preserves_independent_photo_beside_video(self):
        video = TweetMediaItem(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                TweetMediaVariant(
                    url = "https://video.twimg.com/video.mp4",
                    content_type = "video/mp4",
                    bit_rate = 512000,
                ),
            ],
        )
        photo = TweetMediaItem(
            url = "https://pbs.twimg.com/media/photo.jpg",
            preview_url = None,
            media_type = "photo",
        )
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet([video, photo])
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertEqual(len(post.media), 2)
        self.assertEqual([media.kind for media in post.media], [SocialMediaKind.VIDEO, SocialMediaKind.IMAGE])
        self.assertEqual(post.media[1].url, photo.url)
        self.assertNotIn(video.preview_url, [media.url for media in post.media])

    def test_twitter_provider_keeps_static_video_poster_when_no_mp4_variant_exists(self):
        video = TweetMediaItem(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                TweetMediaVariant(
                    url = "https://video.twimg.com/video.m3u8",
                    content_type = "application/x-mpegURL",
                    bit_rate = None,
                ),
            ],
        )
        mock_fetcher = MagicMock()
        mock_fetcher.as_structured.return_value = _make_tweet([video])
        self.mock_di.twitter_status_fetcher.return_value = mock_fetcher
        provider = TwitterSocialPostProvider(self.mock_di, self.mock_x_api_tool, self.mock_vision_tool)

        post = provider.fetch("https://x.com/user/status/123456789")

        self.assertEqual(len(post.media), 1)
        self.assertEqual(post.media[0].preview_url, video.preview_url)
        self.assertIsNone(post.media[0].dynamic_media)


class PhotoDownloaderPathTest(unittest.TestCase):

    @patch("features.web_browsing.photo_downloader.requests.get")
    def test_download_to_streams_chunks_to_path(self, mock_get):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"first", b"", b"second"]
        mock_get.return_value = response

        with TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "photo.jpg"

            result = PhotoDownloader().download_to("https://example.com/photo.jpg", destination)

            self.assertTrue(result)
            self.assertEqual(destination.read_bytes(), b"firstsecond")
        self.assertTrue(mock_get.call_args.kwargs["stream"])

    @patch("features.web_browsing.photo_downloader.requests.get")
    def test_download_to_removes_partial_file_after_failure(self, mock_get):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.side_effect = RuntimeError("connection lost")
        mock_get.return_value = response

        with TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "photo.jpg"

            result = PhotoDownloader().download_to("https://example.com/photo.jpg", destination)

            self.assertFalse(result)
            self.assertFalse(destination.exists())
