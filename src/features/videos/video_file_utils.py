import json
import math
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from typing import Generator

import requests

from util import log
from util.config import config
from util.error_codes import VIDEO_PREPARATION_FAILED, VIDEO_RUNTIME_MISSING
from util.errors import ConfigurationError, ExternalServiceError
from util.functions import delete_file_safe

PROCESS_TIMEOUT_SECONDS = 300
DOWNLOAD_CHUNK_SIZE = 1024 * 1024

# generation workers are cheap pollers, but downloads and transcodes are memory- and CPU-heavy
VIDEO_PREPARATION_SLOTS = BoundedSemaphore(2)

VIDEO_CODEC = "h264"
AUDIO_CODEC = "aac"
PIXEL_FORMAT = "yuv420p"
AUDIO_BITRATE = 128_000
MIN_VIDEO_BITRATE = 100_000

# leave ten percent of the byte limit for container overhead and bitrate variance
OUTPUT_BUDGET_RATIO = 0.90

# each retry lowers both resolution and bitrate so an oversized first pass can converge predictably
TRANSCODE_ATTEMPTS = (
    (1.00, 1.00),
    (0.75, 0.80),
    (0.50, 0.65),
)


@dataclass(frozen = True)
class VideoMetadata:
    """Normalized FFprobe metadata used to decide whether a video can be sent unchanged."""

    # FFprobe groups MP4, MOV, and 3GP under aliases, so the file brand resolves the actual container
    container: str

    # codec and pixel-format tuples contain one entry for each matching stream
    video_codecs: tuple[str, ...]
    audio_codecs: tuple[str, ...]
    pixel_formats: tuple[str, ...]
    video_stream_count: int
    audio_stream_count: int
    width: int
    height: int
    duration_seconds: float
    size_bytes: int

    # MP4 fast start means the metadata atom appears before the media-data atom
    has_fast_start: bool


def inspect_video(input_path: str) -> VideoMetadata:
    """Inspect one local video without decoding its media content."""

    result = _run_process(
        [
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            input_path,
        ],
        "ffprobe",
    )
    if not result.stdout.strip():
        raise ExternalServiceError("FFprobe returned an empty response", VIDEO_PREPARATION_FAILED)

    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ExternalServiceError("FFprobe returned invalid metadata", VIDEO_PREPARATION_FAILED)
        streams = payload.get("streams") or []
        format_data = payload.get("format") or {}
        if (
            not isinstance(streams, list)
            or any(not isinstance(stream, dict) for stream in streams)
            or not isinstance(format_data, dict)
        ):
            raise ExternalServiceError("FFprobe returned invalid metadata", VIDEO_PREPARATION_FAILED)
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not video_streams:
            raise ExternalServiceError("Video file contains no video stream", VIDEO_PREPARATION_FAILED)

        primary_video = video_streams[0]
        width = int(primary_video.get("width") or 0)
        height = int(primary_video.get("height") or 0)
        if width <= 0 or height <= 0:
            raise ExternalServiceError("Video dimensions are missing or invalid", VIDEO_PREPARATION_FAILED)
        duration_seconds = _resolve_duration(format_data, streams)
        if duration_seconds <= 0:
            raise ExternalServiceError("Video duration is missing or invalid", VIDEO_PREPARATION_FAILED)

        container_formats = tuple(
            part.strip()
            for part in str(format_data.get("format_name") or "").split(",")
            if part.strip()
        )
        iso_container, has_fast_start = _inspect_iso_media_layout(input_path)
        container = iso_container or ("webm" if "webm" in container_formats else next(iter(container_formats), ""))
        return VideoMetadata(
            container = container,
            video_codecs = tuple(str(stream.get("codec_name") or "") for stream in video_streams),
            audio_codecs = tuple(str(stream.get("codec_name") or "") for stream in audio_streams),
            pixel_formats = tuple(str(stream.get("pix_fmt") or "") for stream in video_streams),
            video_stream_count = len(video_streams),
            audio_stream_count = len(audio_streams),
            width = width,
            height = height,
            duration_seconds = duration_seconds,
            size_bytes = Path(input_path).stat().st_size,
            has_fast_start = container == "mp4" and has_fast_start,
        )
    except ExternalServiceError:
        raise
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
        raise ExternalServiceError("Could not inspect video metadata", VIDEO_PREPARATION_FAILED) from e


def video_meets_constraints(
    metadata: VideoMetadata,
    max_size_bytes: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> bool:
    """Return whether a video already satisfies the common native-delivery contract."""

    if metadata.container != "mp4":
        return False
    if metadata.video_stream_count != 1 or metadata.video_codecs != (VIDEO_CODEC,):
        return False
    if metadata.audio_stream_count > 1 or any(codec != AUDIO_CODEC for codec in metadata.audio_codecs):
        return False
    if metadata.pixel_formats != (PIXEL_FORMAT,) or not metadata.has_fast_start:
        return False
    if max_size_bytes is not None and metadata.size_bytes > max_size_bytes:
        return False
    if max_width is not None and metadata.width > max_width:
        return False
    return max_height is None or metadata.height <= max_height


def calculate_target_video_bitrate(
    max_size_bytes: int,
    duration_seconds: float,
    has_audio: bool,
) -> int:
    """Calculate the video bitrate left after reserving space for audio and container overhead."""

    available_bitrate = math.floor(max_size_bytes * 8 * OUTPUT_BUDGET_RATIO / duration_seconds)
    video_bitrate = available_bitrate - (AUDIO_BITRATE if has_audio else 0)
    if video_bitrate < MIN_VIDEO_BITRATE:
        raise ExternalServiceError("Video byte limit is too small for its duration", VIDEO_PREPARATION_FAILED)
    return video_bitrate


def prepare_video(
    input_path: str,
    max_size_bytes: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> str:
    """
    Return the input unchanged when compliant, otherwise return a prepared temporary MP4.

    The caller owns a returned temporary path and must delete it after use.
    """

    source_metadata = inspect_video(input_path)
    if video_meets_constraints(source_metadata, max_size_bytes, max_width, max_height):
        return input_path

    target_width, target_height = _resolve_target_dimensions(source_metadata, max_width, max_height)
    target_bitrate = (
        calculate_target_video_bitrate(
            max_size_bytes,
            source_metadata.duration_seconds,
            has_audio = source_metadata.audio_stream_count > 0,
        )
        if max_size_bytes is not None
        else None
    )
    output_path: str | None = None
    prepared_successfully = False

    try:
        attempts = TRANSCODE_ATTEMPTS if max_size_bytes is not None else TRANSCODE_ATTEMPTS[:1]
        for resolution_scale, bitrate_scale in attempts:
            delete_file_safe(output_path)
            output_path = _create_temp_path(".mp4")
            width = _even_dimension(target_width * resolution_scale)
            height = _even_dimension(target_height * resolution_scale)
            bitrate = math.floor(target_bitrate * bitrate_scale) if target_bitrate else None

            _transcode_video(
                input_path = input_path,
                output_path = output_path,
                width = width,
                height = height,
                video_bitrate = bitrate,
                has_audio = source_metadata.audio_stream_count > 0,
            )
            prepared_metadata = inspect_video(output_path)
            if video_meets_constraints(prepared_metadata, max_size_bytes, max_width, max_height):
                prepared_successfully = True
                return output_path

        raise ExternalServiceError("Could not prepare video within destination limits", VIDEO_PREPARATION_FAILED)
    finally:
        if not prepared_successfully:
            delete_file_safe(output_path)


def download_video(public_url: str) -> str:
    """Stream a remote video to a caller-owned temporary file."""

    output_path = _create_temp_path(".video")
    try:
        with Path(output_path).open("wb") as output:
            with requests.get(
                public_url,
                timeout = config.web_timeout_s * 3,
                stream = True,
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size = DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        output.write(chunk)
        if Path(output_path).stat().st_size == 0:
            raise ExternalServiceError("Downloaded video is empty", VIDEO_PREPARATION_FAILED)
        return output_path
    except ExternalServiceError:
        delete_file_safe(output_path)
        raise
    except (OSError, requests.RequestException) as e:
        delete_file_safe(output_path)
        raise ExternalServiceError("Could not download video", VIDEO_PREPARATION_FAILED) from e


@contextmanager
def prepared_remote_video(
    public_url: str,
    max_size_bytes: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> Generator[tuple[str, str, VideoMetadata], None, None]:
    """
    Download and prepare a remote video, then remove every temporary file on exit.

    The preparation slot is held only while downloading, inspecting, and transcoding.
    Callers can archive or send the yielded paths without blocking another preparation.
    """

    original_path: str | None = None
    prepared_path: str | None = None
    try:
        with VIDEO_PREPARATION_SLOTS:
            original_path = download_video(public_url)
            prepared_path = prepare_video(
                original_path,
                max_size_bytes = max_size_bytes,
                max_width = max_width,
                max_height = max_height,
            )
            metadata = inspect_video(prepared_path)
        yield original_path, prepared_path, metadata
    finally:
        delete_file_safe(prepared_path)
        if original_path != prepared_path:
            delete_file_safe(original_path)


def _run_process(command: list[str], executable: str) -> subprocess.CompletedProcess[str]:
    if shutil.which(executable) is None:
        raise ConfigurationError(f"Required video runtime '{executable}' is unavailable", VIDEO_RUNTIME_MISSING)

    try:
        result = subprocess.run(
            command,
            capture_output = True,
            check = False,
            text = True,
            timeout = PROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise ExternalServiceError(f"Video runtime '{executable}' timed out", VIDEO_PREPARATION_FAILED) from e
    except OSError as e:
        raise ExternalServiceError(f"Could not execute video runtime '{executable}'", VIDEO_PREPARATION_FAILED) from e

    if result.returncode != 0:
        detail = (result.stderr.strip() or "unknown error")[-2000:]
        log.w(f"Video runtime '{executable}' failed: {detail}")
        raise ExternalServiceError(f"Video runtime '{executable}' failed", VIDEO_PREPARATION_FAILED)
    return result


def _transcode_video(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    video_bitrate: int | None,
    has_audio: bool,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-pix_fmt", PIXEL_FORMAT,
        "-preset", "medium",
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-movflags", "+faststart",
    ]
    if video_bitrate is None:
        command.extend(["-crf", "23"])
    else:
        command.extend(
            [
                "-b:v", str(video_bitrate),
                "-maxrate", str(video_bitrate),
                "-bufsize", str(video_bitrate * 2),
            ],
        )
    if has_audio:
        command.extend(["-c:a", AUDIO_CODEC, "-b:a", str(AUDIO_BITRATE), "-ac", "2"])
    else:
        command.append("-an")
    command.append(output_path)
    _run_process(command, "ffmpeg")


def _resolve_duration(format_data: dict, streams: list[dict]) -> float:
    raw_duration = format_data.get("duration")
    if raw_duration is not None:
        return float(raw_duration)
    durations = [float(stream["duration"]) for stream in streams if stream.get("duration") is not None]
    return max(durations, default = 0.0)


def _resolve_target_dimensions(
    metadata: VideoMetadata,
    max_width: int | None,
    max_height: int | None,
) -> tuple[int, int]:
    scale = min(
        1.0,
        max_width / metadata.width if max_width and metadata.width else 1.0,
        max_height / metadata.height if max_height and metadata.height else 1.0,
    )
    return _even_dimension(metadata.width * scale), _even_dimension(metadata.height * scale)


def _even_dimension(value: float) -> int:
    return max(2, math.floor(value / 2) * 2)


def _create_temp_path(suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete = False, suffix = suffix) as temp_file:
        return temp_file.name


def _inspect_iso_media_layout(input_path: str) -> tuple[str | None, bool]:
    """
    Identify MP4, MOV, or 3GP and determine whether streaming metadata comes first.

    FFprobe exposes these containers through the same alias list. Their `ftyp` major brand
    distinguishes them. A fast-start MP4 places `moov` before `mdat`, allowing playback
    before the complete file has downloaded. Seeking by box size avoids loading video bytes.
    """

    file_size = Path(input_path).stat().st_size
    with Path(input_path).open("rb") as file:
        offset = 0
        container: str | None = None
        moov_seen = False
        while offset + 8 <= file_size:
            file.seek(offset)
            header = file.read(8)
            box_size = int.from_bytes(header[:4], byteorder = "big")
            box_type = header[4:8]
            header_size = 8

            if box_size == 1:
                extended_size = file.read(8)
                if len(extended_size) != 8:
                    return container, False
                box_size = int.from_bytes(extended_size, byteorder = "big")
                header_size = 16
            elif box_size == 0:
                box_size = file_size - offset

            if box_size < header_size or offset + box_size > file_size:
                return container, False
            if box_type == b"ftyp":
                if box_size < header_size + 4:
                    return container, False
                major_brand = file.read(4)
                if major_brand.startswith((b"3gp", b"3g2")):
                    container = "3gp"
                elif major_brand == b"qt  ":
                    container = "mov"
                else:
                    container = "mp4"
            if box_type == b"moov":
                moov_seen = True
            if box_type == b"mdat":
                return container, moov_seen
            offset += box_size
    return container, False
