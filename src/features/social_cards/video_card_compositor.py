import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw

from features.social_cards.domain import SocialMediaPlacement
from features.videos.video_file_utils import VIDEO_PREPARATION_SLOTS, inspect_video, video_meets_constraints
from util import log
from util.config import config
from util.error_codes import (
    INVALID_SOCIAL_CARD_VIDEO_CONFIGURATION,
    SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
    VIDEO_RUNTIME_MISSING,
)
from util.errors import ConfigurationError, ExternalServiceError

PROCESS_TIMEOUT_SECONDS = 300
OUTPUT_FRAME_RATE = 30
MASK_SCALE = 4


def compose(
    static_card_path: Path,
    media_path: Path,
    placement: SocialMediaPlacement,
    output_path: Path,
) -> None:
    max_duration_seconds = config.social_card_video_max_duration_s
    if max_duration_seconds <= 0:
        raise ConfigurationError(
            "Social-card video duration limit must be positive",
            INVALID_SOCIAL_CARD_VIDEO_CONFIGURATION,
        )

    mask_path = output_path.with_name(f"{uuid4().hex}-mask.png")
    output_path.unlink(missing_ok = True)
    try:
        canvas_width, canvas_height = _validate_inputs(static_card_path, media_path, placement)
        _write_mask(mask_path, placement)

        with VIDEO_PREPARATION_SLOTS:
            source_metadata = inspect_video(str(media_path))
            duration_seconds = min(source_metadata.duration_seconds, max_duration_seconds)
            if duration_seconds <= 0:
                raise ExternalServiceError(
                    "Social-card video duration is invalid",
                    SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
                )
            _run_ffmpeg(
                static_card_path = static_card_path,
                media_path = media_path,
                mask_path = mask_path,
                placement = placement,
                output_path = output_path,
                duration_seconds = duration_seconds,
                has_audio = source_metadata.audio_stream_count > 0,
            )
            _validate_output(output_path, canvas_width, canvas_height, duration_seconds)
    except (ConfigurationError, ExternalServiceError):
        output_path.unlink(missing_ok = True)
        raise
    except (OSError, TypeError, ValueError) as e:
        output_path.unlink(missing_ok = True)
        raise ExternalServiceError(
            "Social-card video composition failed",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        ) from e
    finally:
        mask_path.unlink(missing_ok = True)


def _validate_inputs(
    static_card_path: Path,
    media_path: Path,
    placement: SocialMediaPlacement,
) -> tuple[int, int]:
    if not static_card_path.is_file() or static_card_path.stat().st_size == 0:
        raise ExternalServiceError(
            "Static social card is missing or empty",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )
    if not media_path.is_file() or media_path.stat().st_size == 0:
        raise ExternalServiceError(
            "Social-card video source is missing or empty",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )
    try:
        with Image.open(static_card_path) as static_card:
            canvas_width, canvas_height = static_card.size
    except OSError as e:
        raise ExternalServiceError(
            "Static social card is invalid",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        ) from e

    if (
        canvas_width <= 0
        or canvas_height <= 0
        or placement.x < 0
        or placement.y < 0
        or placement.width <= 0
        or placement.height <= 0
        or placement.x + placement.width > canvas_width
        or placement.y + placement.height > canvas_height
        or any(radius < 0 for radius in _radii(placement))
        or any(radius * 2 > min(placement.width, placement.height) for radius in _radii(placement))
    ):
        raise ExternalServiceError(
            "Social-card video placement is invalid",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )
    return canvas_width, canvas_height


def _write_mask(mask_path: Path, placement: SocialMediaPlacement) -> None:
    width = placement.width * MASK_SCALE
    height = placement.height * MASK_SCALE
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    top_left, top_right, bottom_right, bottom_left = (
        radius * MASK_SCALE
        for radius in _radii(placement)
    )
    _round_corner(draw, width, height, top_left, "top_left")
    _round_corner(draw, width, height, top_right, "top_right")
    _round_corner(draw, width, height, bottom_right, "bottom_right")
    _round_corner(draw, width, height, bottom_left, "bottom_left")
    mask.resize((placement.width, placement.height), Image.Resampling.LANCZOS).save(mask_path, format = "PNG")


def _round_corner(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    radius: int,
    corner: str,
) -> None:
    if radius == 0:
        return
    match corner:
        case "top_left":
            draw.rectangle((0, 0, radius - 1, radius - 1), fill = 0)
            draw.pieslice((0, 0, radius * 2 - 1, radius * 2 - 1), 180, 270, fill = 255)
        case "top_right":
            draw.rectangle((width - radius, 0, width - 1, radius - 1), fill = 0)
            draw.pieslice((width - radius * 2, 0, width - 1, radius * 2 - 1), 270, 360, fill = 255)
        case "bottom_right":
            draw.rectangle((width - radius, height - radius, width - 1, height - 1), fill = 0)
            draw.pieslice(
                (width - radius * 2, height - radius * 2, width - 1, height - 1),
                0,
                90,
                fill = 255,
            )
        case "bottom_left":
            draw.rectangle((0, height - radius, radius - 1, height - 1), fill = 0)
            draw.pieslice((0, height - radius * 2, radius * 2 - 1, height - 1), 90, 180, fill = 255)


def _run_ffmpeg(
    static_card_path: Path,
    media_path: Path,
    mask_path: Path,
    placement: SocialMediaPlacement,
    output_path: Path,
    duration_seconds: float,
    has_audio: bool,
) -> None:
    if shutil.which("ffmpeg") is None:
        raise ConfigurationError("Required video runtime 'ffmpeg' is unavailable", VIDEO_RUNTIME_MISSING)

    duration = f"{duration_seconds:.6f}"
    audio_filter = (
        f"[1:a:0]apad,atrim=duration={duration},asetpts=PTS-STARTPTS[audio]"
        if has_audio
        else f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={duration}[audio]"
    )
    filter_graph = ";".join(
        [
            f"[0:v]format=rgba,pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black@0,"
            f"trim=duration={duration},setpts=PTS-STARTPTS[base]",
            f"[1:v]scale={placement.width}:{placement.height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={placement.width}:{placement.height},setsar=1,fps={OUTPUT_FRAME_RATE},"
            f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},"
            f"setpts=PTS-STARTPTS,format=rgba[media]",
            "[2:v]format=gray[mask]",
            "[media][mask]alphamerge[rounded]",
            f"[base][rounded]overlay={placement.x}:{placement.y}:shortest=1:format=auto,format=yuv420p[video]",
            audio_filter,
        ],
    )
    command = [
        "ffmpeg",
        "-v", "error",
        "-y",
        "-loop", "1",
        "-framerate", str(OUTPUT_FRAME_RATE),
        "-i", str(static_card_path),
        "-i", str(media_path),
        "-loop", "1",
        "-framerate", str(OUTPUT_FRAME_RATE),
        "-i", str(mask_path),
        "-filter_complex", filter_graph,
        "-map", "[video]",
        "-map", "[audio]",
        "-t", duration,
        "-r", str(OUTPUT_FRAME_RATE),
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output = True,
            check = False,
            text = True,
            timeout = PROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise ExternalServiceError(
            "Social-card video composition timed out",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        ) from e
    except OSError as e:
        raise ExternalServiceError(
            "Could not execute social-card video composition",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        ) from e
    if result.returncode != 0:
        detail = (result.stderr.strip() or "unknown error")[-2000:]
        log.w(f"Social-card video composition failed: {detail}")
        raise ExternalServiceError(
            "Social-card video composition failed",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )


def _validate_output(
    output_path: Path,
    canvas_width: int,
    canvas_height: int,
    duration_seconds: float,
) -> None:
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ExternalServiceError(
            "Social-card video composition returned an empty output",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )
    metadata = inspect_video(str(output_path))
    expected_width = canvas_width + canvas_width % 2
    expected_height = canvas_height + canvas_height % 2
    if (
        not video_meets_constraints(metadata)
        or metadata.width != expected_width
        or metadata.height != expected_height
        or metadata.audio_stream_count != 1
        or metadata.duration_seconds <= 0
        or abs(metadata.duration_seconds - duration_seconds) > 0.2
    ):
        raise ExternalServiceError(
            "Social-card video composition returned an invalid output",
            SOCIAL_CARD_VIDEO_COMPOSITION_FAILED,
        )


def _radii(placement: SocialMediaPlacement) -> tuple[int, int, int, int]:
    return (
        placement.top_left_radius,
        placement.top_right_radius,
        placement.bottom_right_radius,
        placement.bottom_left_radius,
    )
