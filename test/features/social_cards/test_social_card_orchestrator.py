import json
import subprocess
from functools import partial
from pathlib import Path
from re import compile, escape
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_url_shortener import FakeUrlShortener
from PIL import Image
from requests.exceptions import ConnectionError
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.llm_tools.llm_tool_library import render_social_post
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_5, X_READ_POST
from features.social_cards import card_template
from features.social_cards.providers.twitter_social_post_provider import TwitterSocialPostProvider
from features.social_cards.social_card_models import SocialCardMode, SocialMediaKind
from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
from features.videos.video_file_utils import inspect_video
from features.web_browsing.photo_downloader import PhotoDownloader
from features.web_browsing.twitter_status_fetcher import TweetData
from util.config import config
from util.error_codes import IMAGE_GENERATION_FAILED, INVALID_SOCIAL_CARD_MODE, WEB_FETCH_FAILED
from util.errors import ExternalServiceError, ValidationError


class SocialCardOrchestratorTest(TestCase):

    di: DI
    http: FakeHTTPClient
    bot: FakeTelegramBotAPI
    shortener: FakeUrlShortener
    orchestrator: SocialCardOrchestrator
    provider: TwitterSocialPostProvider
    tweet: TweetData
    root: Path
    workspaces: Path
    post_url: str = "https://x.com/user/status/123456789"
    api_url: str = "https://api.x.com/2/tweets/123456789"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = "123")))
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.shortener = cast(FakeUrlShortener, self.di.url_shortener(self.post_url))
        api_tool = stubs.domain.configured_tool(definition = X_READ_POST, purpose = ToolType.api_twitter)
        vision_tool = stubs.domain.configured_tool(definition = GPT_5_5, purpose = ToolType.vision)
        self.orchestrator = self.di.social_card_orchestrator([api_tool], vision_tool)
        self.provider = self.di.social_post_provider(TwitterSocialPostProvider, api_tool, vision_tool)
        self.tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(profile_image_url = None), media = [], link_previews = [],
        )
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.workspaces = self.root / "workspaces"
        self.workspaces.mkdir()
        # observe resource cleanup without replacing the workspace or its downloader
        self.enterContext(patch(
            "features.social_cards.asset_workspace.TemporaryDirectory",
            new = partial(TemporaryDirectory, dir = self.workspaces),
        ))
        self.enterContext(patch("features.web_browsing.twitter_status_fetcher.sleep", return_value = None))
        logo = self.root / "logo.svg"
        logo.write_bytes(stubs.external.svg_bytes())
        original_logos = config.logos.copy()
        original_cache = card_template._LOGO_CACHE.copy()

        def restore_logos():
            config.logos.clear()
            config.logos.update(original_logos)
            card_template._LOGO_CACHE.clear()
            card_template._LOGO_CACHE.update(original_cache)

        self.addCleanup(restore_logos)
        for key in config.logos:
            config.logos[key] = logo.as_uri()
        card_template._LOGO_CACHE.clear()

    def test_happy_path_returns_image_url(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        attachment = self.di.chat_attachment_service.resolve_image_attachments([], [result.public_url])[0]
        with self.di.attachment_storage.open(attachment) as stream, Image.open(stream) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 0)
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_invalid_url_raises_validation_error(self):
        with self.assertRaises(ValidationError) as context:
            self.orchestrator.execute("https://example.com/not-a-tweet")

        self.assertEqual(context.exception.error_code, WEB_FETCH_FAILED)
        self.assertEqual(self.http.requests, [])

    def test_photo_download_failure_continues(self):
        media = stubs.external.tweet_media_item()
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.url].append(ConnectionError("Download failed"))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertIn(media.url, [url for url, _ in self.http.requests])
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_render_failure_raises_external_service_error(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        # external SVG engine failure is exercised through the real renderer
        with patch("resvg_py.svg_to_bytes", side_effect = RuntimeError("Invalid SVG")):
            with self.assertRaises(ExternalServiceError) as context:
                self.orchestrator.execute(self.post_url)

        self.assertEqual(context.exception.error_code, IMAGE_GENERATION_FAILED)
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_upload_failure_propagates(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        # retain real local storage while simulating an OS write failure
        with patch("shutil.copyfile", side_effect = OSError("Disk full")):
            with self.assertRaises(OSError):
                self.orchestrator.execute(self.post_url)

        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_url_shortener_failure_still_produces_card(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.shortener.error = ExternalServiceError("Shortener unavailable", WEB_FETCH_FAILED)

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertEqual(self.shortener.executions, 1)

    def test_recursive_assets_are_cleaned_after_success(self):
        self.tweet.quoted_tweet_id = "987654321"
        self.tweet.user.profile_image_url = "https://example.com/avatar.jpg"
        self.tweet.media = [stubs.external.tweet_media_item()]
        embedded = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(profile_image_url = "https://example.com/embedded-avatar.jpg"),
            media = [stubs.external.tweet_media_item(url = "https://example.com/embedded.jpg")], link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses["https://api.x.com/2/tweets/987654321"].append(
            stubs.external.http_json_response(stubs.external.x_tweet_response(embedded)),
        )
        urls = [self.tweet.user.profile_image_url, self.tweet.media[0].url, embedded.user.profile_image_url, embedded.media[0].url]  # ruff: ignore[line-too-long]
        for url in urls:
            self.http.responses[url].append(stubs.external.http_response(content = stubs.external.image_bytes()))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertTrue(set(urls).issubset({url for url, _ in self.http.requests}))
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_image_mode_downloads_dynamic_poster_without_playback(self):
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))

        result = self.orchestrator.execute(self.post_url, SocialCardMode.IMAGE)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertEqual([url for url, _ in self.http.requests], [self.api_url, media.preview_url])

    def test_automatic_mode_composes_and_persists_video_for_direct_dynamic_media(self):
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        self.http.responses[media.variants[0].url].append(stubs.external.http_response(content = stubs.external.video_bytes()))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.VIDEO)
        attachment = self.di.chat_attachment_service.resolve_attachments([], [result.public_url])[0]
        with self.di.attachment_storage.temporary_path(attachment) as path:
            self.assertEqual(inspect_video(path).container, "mp4")
        self.assertGreater(attachment.size, 0)
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_requested_video_without_dynamic_media_returns_image(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))

        result = self.orchestrator.execute(self.post_url, SocialCardMode.VIDEO)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)

    def test_embedded_dynamic_media_stays_static_in_automatic_mode(self):
        self.tweet.quoted_tweet_id = "987654321"
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        embedded = stubs.external.tweet_data(user = self.tweet.user, media = [media], link_previews = [])
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses["https://api.x.com/2/tweets/987654321"].append(
            stubs.external.http_json_response(stubs.external.x_tweet_response(embedded)),
        )
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertNotIn(media.variants[0].url, [url for url, _ in self.http.requests])

    def test_only_main_post_dynamic_media_participates_in_video(self):
        main = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        embedded_media = stubs.external.tweet_media_item(
            media_type = "video", preview_url = "https://example.com/embedded.png",
            variants = [stubs.external.tweet_media_variant(url = "https://example.com/embedded.mp4")],
        )
        self.tweet.media = [main]
        self.tweet.quoted_tweet_id = "987654321"
        embedded = stubs.external.tweet_data(user = self.tweet.user, media = [embedded_media], link_previews = [])
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses["https://api.x.com/2/tweets/987654321"].append(
            stubs.external.http_json_response(stubs.external.x_tweet_response(embedded)),
        )
        for url in (main.preview_url, embedded_media.preview_url):
            self.http.responses[url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        self.http.responses[main.variants[0].url].append(stubs.external.http_response(content = stubs.external.video_bytes()))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.VIDEO)
        self.assertNotIn(embedded_media.variants[0].url, [url for url, _ in self.http.requests])

    def test_playback_download_failure_persists_static_fallback_and_cleans_workspace(self):
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        self.http.responses[media.variants[0].url].append(ConnectionError("Playback unavailable"))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertIn(media.variants[0].url, [url for url, _ in self.http.requests])
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_composition_failure_persists_static_fallback(self):
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        self.http.responses[media.variants[0].url].append(stubs.external.http_response(content = stubs.external.video_bytes()))
        run_process = subprocess.run

        def fail_encoding(command, **kwargs):
            if Path(command[0]).name == "ffmpeg":
                return stubs.external.process_result(args = command, returncode = 1, stderr = "Encoding failed")
            return run_process(command, **kwargs)

        # FFprobe and compositor decisions remain real; only the external encoder fails
        with patch.object(subprocess, "run", new = fail_encoding):
            result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.IMAGE)
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_animated_gif_is_composed_as_video(self):
        media = stubs.external.tweet_media_item(media_type = "animated_gif", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        self.http.responses[media.variants[0].url].append(stubs.external.http_response(content = stubs.external.video_bytes()))

        result = self.orchestrator.execute(self.post_url)

        self.assertEqual(result.mode, SocialCardMode.VIDEO)

    def test_render_social_post_routes_video_result_to_video_delivery(self):
        media = stubs.external.tweet_media_item(media_type = "video", variants = [stubs.external.tweet_media_variant()])
        self.tweet.media = [media]
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[media.preview_url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        content = stubs.external.video_bytes()
        self.http.responses[media.variants[0].url].append(stubs.external.http_response(content = content))
        self.http.responses[compile(escape(config.public_api_base_url) + r"/attachments/public/[^/]+")].append(
            stubs.external.http_response(content = content),
        )

        response = json.loads(render_social_post(self.di, self.post_url, mode = "video"))

        self.assertEqual(response["result"], "Success")
        messages = self.bot.get_sent_messages("123")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["metadata"].container, "mp4")
        self.assertGreater(len(messages[0]["content"]), 0)

    def test_render_social_post_routes_requested_video_image_fallback_to_photo_delivery(self):
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
        self.http.responses[compile(escape(config.public_api_base_url) + r"/attachments/public/[^/]+")].append(
            stubs.external.http_response(content = stubs.external.image_bytes()),
        )

        response = json.loads(render_social_post(self.di, self.post_url, mode = "video"))

        self.assertEqual(response["result"], "Success")
        self.assertIn("photo_url", self.bot.get_sent_messages("123")[0])

    def test_render_social_post_passes_image_and_omitted_modes(self):
        for mode in ("image", None):
            with self.subTest(mode = mode):
                self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(self.tweet)))
                self.http.responses[compile(escape(config.public_api_base_url) + r"/attachments/public/[^/]+")].append(
                    stubs.external.http_response(content = stubs.external.image_bytes()),
                )

                response = json.loads(render_social_post(self.di, self.post_url, mode = mode))

                self.assertEqual(response["result"], "Success")
                self.assertIn("photo_url", self.bot.get_sent_messages("123")[-1])

    def test_render_social_post_rejects_invalid_mode(self):
        for mode in ("animated", ""):
            with self.subTest(mode = mode):
                response = json.loads(render_social_post(self.di, self.post_url, mode = mode))

                self.assertEqual(response["result"], "Error")
                self.assertEqual(response["error_code"], INVALID_SOCIAL_CARD_MODE)
        self.assertEqual(self.http.requests, [])

    def test_twitter_provider_transforms_profile_url_normal_to_bigger(self):
        tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(
                name = "Test User",
                handle = "testuser",
                bio = None,
                profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
            ),
            text = "Hello world",
            media = [],
            link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(tweet)))

        post = self.provider.fetch(self.post_url)

        self.assertIn("_bigger", post.author.avatar_url)
        self.assertNotIn("_normal", post.author.avatar_url)

    def test_twitter_provider_selects_highest_bitrate_mp4_video_variant(self):
        video = stubs.external.tweet_media_item(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                stubs.external.tweet_media_variant(
                    url = "https://video.twimg.com/video.m3u8",
                    content_type = "application/x-mpegURL",
                    bit_rate = 4000000,
                ),
                stubs.external.tweet_media_variant(
                    url = "https://video.twimg.com/video-low.mp4",
                    bit_rate = 256000,
                ),
                stubs.external.tweet_media_variant(
                    url = "https://video.twimg.com/video-high.mp4",
                    bit_rate = 1024000,
                ),
            ],
            duration_ms = 12345,
            width = 1920,
            height = 1080,
            alt_text = "A test video",
        )
        tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(
                name = "Test User",
                handle = "testuser",
                bio = None,
                profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
            ),
            text = "Hello world",
            media = [video],
            link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(tweet)))

        post = self.provider.fetch(self.post_url)

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
        animated_gif = stubs.external.tweet_media_item(
            url = None,
            preview_url = "https://pbs.twimg.com/media/gif-preview.jpg",
            media_type = "animated_gif",
            variants = [
                stubs.external.tweet_media_variant(
                    url = "https://video.twimg.com/animation.mp4",
                    bit_rate = None,
                ),
            ],
        )
        tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(
                name = "Test User",
                handle = "testuser",
                bio = None,
                profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
            ),
            text = "Hello world",
            media = [animated_gif],
            link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(tweet)))

        post = self.provider.fetch(self.post_url)

        self.assertEqual(len(post.media), 1)
        self.assertEqual(post.media[0].kind, SocialMediaKind.GIF)
        self.assertEqual(post.media[0].preview_url, animated_gif.preview_url)
        self.assertEqual(post.media[0].dynamic_media.playback_url, "https://video.twimg.com/animation.mp4")

    def test_twitter_provider_preserves_independent_photo_beside_video(self):
        video = stubs.external.tweet_media_item(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                stubs.external.tweet_media_variant(
                    bit_rate = 512000,
                ),
            ],
        )
        photo = stubs.external.tweet_media_item(
            preview_url = None,
        )
        tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(
                name = "Test User",
                handle = "testuser",
                bio = None,
                profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
            ),
            text = "Hello world",
            media = [video, photo],
            link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(tweet)))

        post = self.provider.fetch(self.post_url)

        self.assertEqual(len(post.media), 2)
        self.assertEqual([media.kind for media in post.media], [SocialMediaKind.VIDEO, SocialMediaKind.IMAGE])
        self.assertEqual(post.media[1].url, photo.url)
        self.assertNotIn(video.preview_url, [media.url for media in post.media])

    def test_twitter_provider_keeps_static_video_poster_when_no_mp4_variant_exists(self):
        video = stubs.external.tweet_media_item(
            url = None,
            preview_url = "https://pbs.twimg.com/media/video-preview.jpg",
            media_type = "video",
            variants = [
                stubs.external.tweet_media_variant(
                    url = "https://video.twimg.com/video.m3u8",
                    content_type = "application/x-mpegURL",
                    bit_rate = None,
                ),
            ],
        )
        tweet = stubs.external.tweet_data(
            user = stubs.external.tweet_user_data(
                name = "Test User",
                handle = "testuser",
                bio = None,
                profile_image_url = "https://pbs.twimg.com/profile_images/123/photo_normal.jpg",
            ),
            text = "Hello world",
            media = [video],
            link_previews = [],
        )
        self.http.responses[self.api_url].append(stubs.external.http_json_response(stubs.external.x_tweet_response(tweet)))

        post = self.provider.fetch(self.post_url)

        self.assertEqual(len(post.media), 1)
        self.assertEqual(post.media[0].preview_url, video.preview_url)
        self.assertIsNone(post.media[0].dynamic_media)


class PhotoDownloaderPathTest(TestCase):

    root: Path
    http: FakeHTTPClient
    downloader: PhotoDownloader

    def setUp(self):
        di = self.enterContext(di_for_tests())
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.http = cast(FakeHTTPClient, di.http_client())
        self.downloader = di.photo_downloader()

    def test_download_to_streams_chunks_to_path(self):
        content = b"first" * (1024 * 256) + b"second"
        self.http.responses["https://example.com/photo.jpg"].append(stubs.external.http_response(content = content))
        destination = self.root / "photo.jpg"

        result = self.downloader.download_to("https://example.com/photo.jpg", destination)

        self.assertTrue(result)
        self.assertEqual(destination.read_bytes(), content)
        self.assertTrue(self.http.requests[0][1]["stream"])

    def test_download_to_removes_partial_file_after_failure(self):
        self.http.responses["https://example.com/photo.jpg"].append(ConnectionError("Connection lost"))
        destination = self.root / "photo.jpg"
        destination.write_bytes(b"partial download")

        result = self.downloader.download_to("https://example.com/photo.jpg", destination)

        self.assertFalse(result)
        self.assertFalse(destination.exists())
