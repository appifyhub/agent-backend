import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from features.social_cards import card_renderer, card_template, video_card_compositor
from features.social_cards.card_layout import (
    CARD_INNER_PAD,
    CARD_OUTER_PAD,
    FONT_SIZE_BODY,
    FONT_SIZE_TITLE,
    PHOTO_CORNER_RADIUS,
    card_width_from_text,
)
from features.social_cards.link_preview import prepare_favicon
from features.social_cards.social_card_models import (
    SocialAuthor,
    SocialCardMode,
    SocialCardRenderResult,
    SocialCardTemplateResult,
    SocialCardVideoInput,
    SocialDynamicMedia,
    SocialLinkPreview,
    SocialLinkPreviewAsset,
    SocialMediaAsset,
    SocialMediaItem,
    SocialMediaKind,
    SocialMediaPlacement,
    SocialPlatformBrand,
    SocialPost,
    SocialPostRenderAssets,
)
from features.social_cards.theme import ThemeColors
from features.social_cards.video_card_timeline import plan_timeline
from features.videos.video_file_utils import inspect_video, video_meets_constraints
from util.config import config
from util.error_codes import INVALID_SOCIAL_CARD_VIDEO_CONFIGURATION, SOCIAL_CARD_VIDEO_COMPOSITION_FAILED
from util.errors import ConfigurationError, ExternalServiceError


def _brand() -> SocialPlatformBrand:
    return SocialPlatformBrand(
        platform_id = "x",
        display_name = "X",
        logo_light_key = "x_logo_light",
        logo_dark_key = "x_logo_dark",
    )


def _post() -> SocialPost:
    return SocialPost(
        platform = _brand(),
        author = SocialAuthor(additional_profile_info = "Milos", handle = "@milos"),
        text = "hello world",
        source_url = "https://x.com/milos/status/1",
    )


def _theme() -> ThemeColors:
    return ThemeColors(
        gradient_start = "#251A3D",
        gradient_end = "#040b19",
        text_color = "#ffffff",
    )


def _write_image(path: Path, size: tuple[int, int] = (100, 100)) -> Path:
    Image.new("RGB", size, color = (100, 50, 25)).save(path)
    return path


def _video_placement(
    kind: SocialMediaKind = SocialMediaKind.VIDEO,
    x: int = 20,
    y: int = 30,
    width: int = 100,
    height: int = 80,
) -> SocialMediaPlacement:
    return SocialMediaPlacement(
        media = SocialMediaItem(kind = kind),
        x = x,
        y = y,
        width = width,
        height = height,
        top_left_radius = 20,
        top_right_radius = 20,
        bottom_right_radius = 20,
        bottom_left_radius = 20,
    )


def _video_input(
    media_path: Path,
    placement: SocialMediaPlacement | None = None,
) -> SocialCardVideoInput:
    return SocialCardVideoInput(
        media_path = media_path,
        placement = placement or _video_placement(),
    )


def _run_test_ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *arguments],
        capture_output = True,
        check = True,
    )


def _extract_frame(video_path: Path, output_path: Path, timestamp: float) -> Image.Image:
    _run_test_ffmpeg(
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        str(output_path),
    )
    with Image.open(output_path) as frame:
        return frame.convert("RGB")


def _assert_color(pixel: tuple[int, int, int], expected: tuple[int, int, int], tolerance: int = 40) -> None:
    assert all(abs(actual - target) <= tolerance for actual, target in zip(pixel, expected, strict = True))


def _audio_is_silent(video_path: Path, start: float, duration: float) -> bool:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v", "info",
            "-ss", str(start),
            "-t", str(duration),
            "-i", str(video_path),
            "-map", "0:a:0",
            "-af", "volumedetect",
            "-f", "null",
            "-",
        ],
        capture_output = True,
        check = True,
        text = True,
    )
    for line in result.stderr.splitlines():
        if "max_volume:" not in line:
            continue
        measured_volume = line.partition("max_volume:")[2].split()[0]
        return measured_volume == "-inf" or float(measured_volume) <= -80
    return False


@pytest.fixture(scope = "module")
def video_sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("social-card-video-sources")
    landscape = root / "landscape-audio.mp4"
    portrait = root / "portrait-silent.mp4"
    _run_test_ffmpeg(
        "-f", "lavfi",
        "-i", "color=c=red:size=160x90:rate=30:d=0.5",
        "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=44100:duration=1",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(landscape),
    )
    _run_test_ffmpeg(
        "-f", "lavfi",
        "-i", "color=c=green:size=90x160:rate=30:d=1",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(portrait),
    )
    return {"landscape": landscape, "portrait": portrait}


def test_social_post_domain_holds_platform_neutral_rendering_data(tmp_path: Path) -> None:
    media = SocialMediaItem(
        kind = SocialMediaKind.IMAGE,
        url = "https://example.com/image.jpg",
    )
    link_preview = SocialLinkPreview(
        expanded_url = "https://example.com/article",
        domain = "example.com",
        title = "Example",
    )
    embedded_post = SocialPost(
        platform = _brand(),
        author = SocialAuthor(additional_profile_info = "Other", handle = "@other"),
        text = "embedded",
        source_url = "https://x.com/other/status/2",
    )

    post = SocialPost(
        platform = _brand(),
        author = SocialAuthor(additional_profile_info = "Milos", handle = "@milos", avatar_url = "https://example.com/avatar.jpg"),
        text = "hello world",
        source_url = "https://x.com/milos/status/1",
        media = [media],
        link_previews = [link_preview],
        embedded_post = embedded_post,
    )
    assets = SocialPostRenderAssets(
        avatar_path = tmp_path / "avatar.png",
        media = [SocialMediaAsset(media = media, path = tmp_path / "media.png")],
        link_previews = [SocialLinkPreviewAsset(link_preview = link_preview, favicon_path = tmp_path / "favicon.png")],
        embedded_post = SocialPostRenderAssets(avatar_path = tmp_path / "embedded-avatar.png"),
    )

    assert post.author.handle == "@milos"
    assert post.media[0].kind == SocialMediaKind.IMAGE
    assert post.link_previews[0].domain == "example.com"
    assert post.embedded_post is embedded_post
    assert assets.media[0].media is media
    assert assets.link_previews[0].link_preview is link_preview
    assert assets.embedded_post is not None


def test_dynamic_social_card_contracts_are_platform_neutral() -> None:
    dynamic = SocialDynamicMedia(
        playback_url = "https://example.com/video.mp4",
        duration_seconds = 12.5,
        width = 1920,
        height = 1080,
    )
    media = SocialMediaItem(
        kind = SocialMediaKind.VIDEO,
        preview_url = "https://example.com/poster.jpg",
        dynamic_media = dynamic,
    )
    result = SocialCardRenderResult(
        public_url = "https://example.com/card.mp4",
        mode = SocialCardMode.VIDEO,
    )

    assert SocialCardMode.IMAGE.value == "image"
    assert SocialCardMode.VIDEO.value == "video"
    assert media.dynamic_media is dynamic
    assert result.public_url == "https://example.com/card.mp4"
    assert result.mode == SocialCardMode.VIDEO


def test_card_renderer_writes_png_to_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    post = _post()
    assets = SocialPostRenderAssets()
    captured: dict[str, object] = {}

    def fake_build_svg(**kwargs: object) -> SocialCardTemplateResult:
        captured.update(kwargs)
        return SocialCardTemplateResult(svg = "<svg></svg>", width = 100, height = 200)

    monkeypatch.setattr(card_renderer, "build_svg", fake_build_svg)
    monkeypatch.setattr(card_renderer.resvg_py, "svg_to_bytes", lambda **kwargs: b"png")

    output_path = tmp_path / "card.png"
    result = card_renderer.render(
        post = post,
        theme = _theme(),
        assets = assets,
        output_path = output_path,
        short_url = post.source_url,
    )

    assert result.width == 100
    assert output_path.read_bytes() == b"png"
    assert captured["post"] is post
    assert captured["assets"] is assets


def test_card_template_consumes_neutral_social_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert "hello world" in result.svg
    assert "x.com/milos/status/1" in result.svg


def test_titled_post_renders_bold_title_above_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()
    post.title = "Breaking News"

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert f'font-size="{FONT_SIZE_TITLE}"' in result.svg
    assert "Breaking News" in result.svg
    title_index = result.svg.index("Breaking News")
    body_index = result.svg.index("hello world")
    assert title_index < body_index


def test_title_wraps_across_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()
    post.title = " ".join(["extraordinarily-long-title-word"] * 40)

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert result.svg.count(f'font-size="{FONT_SIZE_TITLE}"') > 1


def test_title_only_post_reserves_no_body_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()
    post.title = "Just a title"
    post.text = ""

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert "Just a title" in result.svg
    assert f'font-size="{FONT_SIZE_BODY}"' not in result.svg


def test_untitled_post_renders_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    post = _post()

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = SocialPostRenderAssets(),
        short_url = post.source_url,
    )

    assert post.title is None
    assert f'font-size="{FONT_SIZE_TITLE}"' not in result.svg
    assert "hello world" in result.svg


def test_card_width_from_text_includes_title_length() -> None:
    body = "x" * 400
    assert card_width_from_text(body) == 800
    assert card_width_from_text(body, "y" * 200) == 1000


def test_card_renderer_resolves_local_image_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        card_template,
        "_fetch_logo",
        lambda key: (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            b'<circle cx="5" cy="5" r="4" fill="white"/></svg>'
        ),
    )
    media = SocialMediaItem(kind = SocialMediaKind.IMAGE, url = "https://example.com/photo.jpg")
    link_preview = SocialLinkPreview(
        expanded_url = "https://example.com/article",
        domain = "example.com",
        title = "Example article",
    )
    favicon_path = prepare_favicon(
        _write_image(tmp_path / "favicon-source.png"),
        tmp_path / "favicon.png",
    )
    assets = SocialPostRenderAssets(
        avatar_path = _write_image(tmp_path / "avatar.png"),
        media = [SocialMediaAsset(media = media, path = _write_image(tmp_path / "photo.png", (160, 90)))],
        link_previews = [
            SocialLinkPreviewAsset(
                link_preview = link_preview,
                og_image_path = _write_image(tmp_path / "og-image.png", (300, 200)),
                favicon_path = favicon_path,
            ),
        ],
    )
    output_path = tmp_path / "card.png"

    result = card_renderer.render(
        post = _post(),
        theme = _theme(),
        assets = assets,
        output_path = output_path,
        short_url = "https://short.example/1",
    )

    with Image.open(output_path) as rendered:
        assert rendered.size == (result.width, result.height)
        assert rendered.format == "PNG"
        placement = result.media_placements[0]
        center = (placement.x + placement.width // 2, placement.y + placement.height // 2)
        assert rendered.convert("RGB").getpixel(center) == (100, 50, 25)


def test_dynamic_media_is_full_width_before_tiled_photos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(card_template, "_fetch_logo", lambda key: b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    video_one = SocialMediaItem(
        kind = SocialMediaKind.VIDEO,
        preview_url = "https://example.com/video-one.jpg",
        dynamic_media = SocialDynamicMedia(playback_url = "https://example.com/video-one.mp4"),
    )
    photo_one = SocialMediaItem(kind = SocialMediaKind.IMAGE, url = "https://example.com/photo-one.jpg")
    video_two = SocialMediaItem(
        kind = SocialMediaKind.GIF,
        preview_url = "https://example.com/video-two.jpg",
        dynamic_media = SocialDynamicMedia(playback_url = "https://example.com/video-two.mp4"),
    )
    photo_two = SocialMediaItem(kind = SocialMediaKind.IMAGE, url = "https://example.com/photo-two.jpg")
    post = _post()
    post.media = [photo_one, video_one, photo_two, video_two]
    assets = SocialPostRenderAssets(
        media = [
            SocialMediaAsset(media = photo_one, path = _write_image(tmp_path / "photo-one.png")),
            SocialMediaAsset(media = video_one, path = _write_image(tmp_path / "video-one.png", (160, 90))),
            SocialMediaAsset(media = photo_two, path = _write_image(tmp_path / "photo-two.png")),
            SocialMediaAsset(media = video_two, path = _write_image(tmp_path / "video-two.png", (160, 90))),
        ],
    )

    result = card_template.build_svg(
        post = post,
        theme = _theme(),
        card_width = 800,
        assets = assets,
        short_url = post.source_url,
    )

    assert [placement.media for placement in result.media_placements] == [video_one, video_two, photo_one, photo_two]
    for placement in result.media_placements[:2]:
        assert placement.x == CARD_OUTER_PAD + CARD_INNER_PAD
        assert placement.width == 800 - 2 * CARD_INNER_PAD
        assert (
            placement.top_left_radius,
            placement.top_right_radius,
            placement.bottom_right_radius,
            placement.bottom_left_radius,
        ) == (PHOTO_CORNER_RADIUS,) * 4
    assert result.media_placements[2].y > result.media_placements[1].y
    assert str(tmp_path.resolve()) in result.svg


def test_video_card_compositor_preserves_audio_freezes_last_frame_and_masks_corners(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 201), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    mask_path = tmp_path / "known-mask.png"
    monkeypatch.setattr(video_card_compositor, "uuid4", lambda: SimpleNamespace(hex = "known"))

    video_card_compositor.compose(
        static_card_path,
        [_video_input(video_sources["landscape"])],
        output_path,
    )

    metadata = inspect_video(str(output_path))
    assert video_meets_constraints(metadata)
    assert (metadata.width, metadata.height) == (200, 202)
    assert metadata.audio_stream_count == 1
    assert metadata.duration_seconds == pytest.approx(1, abs = 0.1)
    assert not mask_path.exists()

    placement = _video_placement()
    early_frame = _extract_frame(output_path, tmp_path / "early.png", 0.2)
    late_frame = _extract_frame(output_path, tmp_path / "late.png", 0.9)
    for frame in (early_frame, late_frame):
        _assert_color(frame.getpixel((placement.x + placement.width // 2, placement.y + placement.height // 2)), (255, 0, 0))
        for corner in (
            (placement.x, placement.y),
            (placement.x + placement.width - 1, placement.y),
            (placement.x + placement.width - 1, placement.y + placement.height - 1),
            (placement.x, placement.y + placement.height - 1),
        ):
            _assert_color(frame.getpixel(corner), (255, 255, 0))


def test_video_card_compositor_scales_portrait_video_and_generates_silent_audio(
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 240), color = "blue").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    placement = _video_placement(height = 178)

    video_card_compositor.compose(
        static_card_path,
        [_video_input(video_sources["portrait"], placement)],
        output_path,
    )

    metadata = inspect_video(str(output_path))
    assert video_meets_constraints(metadata)
    assert metadata.audio_stream_count == 1
    frame = _extract_frame(output_path, tmp_path / "portrait.png", 0.5)
    _assert_color(frame.getpixel((placement.x - 2, placement.y + placement.height // 2)), (0, 0, 255))
    _assert_color(frame.getpixel((placement.x + 2, placement.y + placement.height // 2)), (0, 128, 0))
    _assert_color(frame.getpixel((placement.x + placement.width // 2, placement.y + placement.height // 2)), (0, 128, 0))


def test_video_card_compositor_trims_to_configured_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 200), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    monkeypatch.setattr(config, "social_card_video_max_duration_s", 0.4)

    video_card_compositor.compose(
        static_card_path,
        [_video_input(video_sources["landscape"])],
        output_path,
    )

    assert inspect_video(str(output_path)).duration_seconds == pytest.approx(0.4, abs = 0.1)


def test_video_card_compositor_rejects_invalid_duration_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config, "social_card_video_max_duration_s", 0)
    output_path = tmp_path / "card.mp4"

    with pytest.raises(ConfigurationError) as error:
        video_card_compositor.compose(
            tmp_path / "static.png",
            [],
            output_path,
        )

    assert error.value.error_code == INVALID_SOCIAL_CARD_VIDEO_CONFIGURATION
    assert not output_path.exists()


def test_video_card_compositor_removes_partial_output_and_mask_after_process_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 200), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    mask_path = tmp_path / "known-mask.png"
    source_metadata = inspect_video(str(video_sources["landscape"]))
    monkeypatch.setattr(video_card_compositor, "inspect_video", lambda path: source_metadata)
    monkeypatch.setattr(video_card_compositor, "uuid4", lambda: SimpleNamespace(hex = "known"))

    def fail_process(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        output_path.write_bytes(b"partial")
        return subprocess.CompletedProcess(command, returncode = 1, stdout = "", stderr = "failed")

    monkeypatch.setattr(video_card_compositor.subprocess, "run", fail_process)

    with pytest.raises(ExternalServiceError) as error:
        video_card_compositor.compose(
            static_card_path,
            [_video_input(video_sources["landscape"])],
            output_path,
        )

    assert error.value.error_code == SOCIAL_CARD_VIDEO_COMPOSITION_FAILED
    assert not output_path.exists()
    assert not mask_path.exists()


def test_video_card_compositor_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 200), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    source_metadata = inspect_video(str(video_sources["landscape"]))
    monkeypatch.setattr(video_card_compositor, "inspect_video", lambda path: source_metadata)

    def time_out_process(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["ffmpeg"], 300)

    monkeypatch.setattr(video_card_compositor.subprocess, "run", time_out_process)

    with pytest.raises(ExternalServiceError) as error:
        video_card_compositor.compose(
            static_card_path,
            [_video_input(video_sources["landscape"])],
            output_path,
        )

    assert error.value.error_code == SOCIAL_CARD_VIDEO_COMPOSITION_FAILED
    assert "timed out" in str(error.value)
    assert not output_path.exists()


def test_video_card_compositor_rejects_empty_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (200, 200), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"
    source_metadata = inspect_video(str(video_sources["landscape"]))
    monkeypatch.setattr(video_card_compositor, "inspect_video", lambda path: source_metadata)
    monkeypatch.setattr(
        video_card_compositor.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, returncode = 0, stdout = "", stderr = ""),
    )

    with pytest.raises(ExternalServiceError) as error:
        video_card_compositor.compose(
            static_card_path,
            [_video_input(video_sources["landscape"])],
            output_path,
        )

    assert error.value.error_code == SOCIAL_CARD_VIDEO_COMPOSITION_FAILED
    assert "empty output" in str(error.value)


def test_video_card_timeline_plans_source_order_under_one_accumulated_cap() -> None:
    timeline = plan_timeline([80.0, 80.0, 10.0], max_duration_seconds = 120.0)

    assert [(segment.source_index, segment.start_seconds, segment.duration_seconds) for segment in timeline] == [
        (0, 0.0, 80.0),
        (1, 80.0, 40.0),
    ]
    assert timeline[-1].end_seconds == 120.0


def test_video_card_compositor_plays_videos_sequentially_with_active_audio_only(
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    static_card = Image.new("RGB", (160, 220), color = "black")
    static_card.paste("yellow", (20, 20, 120, 100))
    static_card.paste("blue", (20, 120, 120, 200))
    static_card.save(static_card_path)
    output_path = tmp_path / "card.mp4"
    first_placement = _video_placement(y = 20)
    second_placement = _video_placement(y = 120)

    video_card_compositor.compose(
        static_card_path,
        [
            _video_input(video_sources["landscape"], first_placement),
            _video_input(video_sources["portrait"], second_placement),
        ],
        output_path,
    )

    assert inspect_video(str(output_path)).duration_seconds == pytest.approx(2, abs = 0.1)
    first_segment = _extract_frame(output_path, tmp_path / "first-segment.png", 0.5)
    second_segment = _extract_frame(output_path, tmp_path / "second-segment.png", 1.8)
    _assert_color(first_segment.getpixel((70, 60)), (255, 0, 0))
    _assert_color(first_segment.getpixel((70, 160)), (0, 0, 255))
    _assert_color(second_segment.getpixel((70, 60)), (255, 0, 0))
    _assert_color(second_segment.getpixel((70, 160)), (0, 128, 0))
    assert not _audio_is_silent(output_path, start = 0.1, duration = 0.7)
    assert _audio_is_silent(output_path, start = 1.1, duration = 0.7)


def test_video_card_compositor_plays_video_then_gif_with_silent_gif_audio(
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    static_card = Image.new("RGB", (160, 220), color = "black")
    static_card.paste("yellow", (20, 20, 120, 100))
    static_card.paste("blue", (20, 120, 120, 200))
    static_card.save(static_card_path)
    output_path = tmp_path / "card.mp4"

    video_card_compositor.compose(
        static_card_path,
        [
            _video_input(video_sources["portrait"], _video_placement(y = 20)),
            _video_input(
                video_sources["landscape"],
                _video_placement(kind = SocialMediaKind.GIF, y = 120),
            ),
        ],
        output_path,
    )

    gif_segment = _extract_frame(output_path, tmp_path / "gif-segment.png", 1.5)
    _assert_color(gif_segment.getpixel((70, 60)), (0, 128, 0))
    _assert_color(gif_segment.getpixel((70, 160)), (255, 0, 0))
    assert _audio_is_silent(output_path, start = 0.1, duration = 1.7)


def test_video_card_compositor_keeps_gif_only_output_silent(
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    Image.new("RGB", (160, 120), color = "yellow").save(static_card_path)
    output_path = tmp_path / "card.mp4"

    video_card_compositor.compose(
        static_card_path,
        [
            _video_input(
                video_sources["landscape"],
                _video_placement(kind = SocialMediaKind.GIF, y = 20),
            ),
        ],
        output_path,
    )

    assert inspect_video(str(output_path)).audio_stream_count == 1
    assert _audio_is_silent(output_path, start = 0.1, duration = 0.7)


def test_video_card_compositor_truncates_active_item_and_does_not_start_later_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    video_sources: dict[str, Path],
) -> None:
    static_card_path = tmp_path / "static.png"
    static_card = Image.new("RGB", (160, 320), color = "black")
    static_card.paste("yellow", (20, 20, 120, 100))
    static_card.paste("blue", (20, 120, 120, 200))
    static_card.paste("magenta", (20, 220, 120, 300))
    static_card.save(static_card_path)
    output_path = tmp_path / "card.mp4"
    monkeypatch.setattr(config, "social_card_video_max_duration_s", 1.5)

    video_card_compositor.compose(
        static_card_path,
        [
            _video_input(video_sources["landscape"], _video_placement(y = 20)),
            _video_input(video_sources["portrait"], _video_placement(y = 120)),
            _video_input(video_sources["landscape"], _video_placement(y = 220)),
        ],
        output_path,
    )

    assert inspect_video(str(output_path)).duration_seconds == pytest.approx(1.5, abs = 0.1)
    final_segment = _extract_frame(output_path, tmp_path / "final-segment.png", 1.4)
    _assert_color(final_segment.getpixel((70, 60)), (255, 0, 0))
    _assert_color(final_segment.getpixel((70, 160)), (0, 128, 0))
    _assert_color(final_segment.getpixel((70, 260)), (255, 0, 255))
