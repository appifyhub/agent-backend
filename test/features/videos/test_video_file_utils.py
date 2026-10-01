import subprocess
import tempfile
import unittest
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import cast
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from util.di_utils import di_for_tests

from features.videos import video_file_utils
from util.error_codes import VIDEO_PREPARATION_FAILED, VIDEO_RUNTIME_MISSING
from util.errors import ConfigurationError, ExternalServiceError


class VideoFileUtilsTest(unittest.TestCase):

    _fixture_directory: TemporaryDirectory[str]
    compliant_path: Path
    no_fast_start_path: Path
    webm_path: Path
    root: Path
    http: FakeHTTPClient
    _temp_paths: list[str]

    @classmethod
    def setUpClass(cls):
        cls._fixture_directory = tempfile.TemporaryDirectory()
        fixture_root = Path(cls._fixture_directory.name)
        cls.compliant_path = fixture_root / "compliant.mp4"
        cls.no_fast_start_path = fixture_root / "no-fast-start.mp4"
        cls.webm_path = fixture_root / "source.webm"

        cls._run_ffmpeg(
            "-f", "lavfi",
            "-i", "testsrc2=size=160x90:rate=10",
            "-f", "lavfi",
            "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "1",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(cls.compliant_path),
        )
        cls._run_ffmpeg(
            "-i", str(cls.compliant_path),
            "-c", "copy",
            str(cls.no_fast_start_path),
        )
        cls._run_ffmpeg(
            "-i", str(cls.compliant_path),
            "-c:v", "libvpx-vp9",
            "-deadline", "realtime",
            "-cpu-used", "8",
            "-c:a", "libopus",
            str(cls.webm_path),
        )

    @classmethod
    def tearDownClass(cls):
        cls._fixture_directory.cleanup()

    @classmethod
    def _run_ffmpeg(cls, *arguments: str):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *arguments],
            capture_output = True,
            check = True,
        )

    def setUp(self):
        self._temp_paths = []
        self.root = Path(self.enterContext(TemporaryDirectory()))
        di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, di.http_client())
        # keep system-created temporary files in a directory whose cleanup we can observe
        self.enterContext(patch.object(tempfile, "NamedTemporaryFile", new = partial(NamedTemporaryFile, dir = self.root)))

    def tearDown(self):
        for path in self._temp_paths:
            Path(path).unlink(missing_ok = True)

    def _temp_path(self, suffix: str = ".mp4") -> str:
        with tempfile.NamedTemporaryFile(delete = False, suffix = suffix) as temp_file:
            path = temp_file.name
        self._temp_paths.append(path)
        return path

    def test_inspect_video_reads_delivery_metadata(self):
        metadata = video_file_utils.inspect_video(str(self.compliant_path))

        self.assertEqual(metadata.container, "mp4")
        self.assertEqual(metadata.video_codecs, ("h264",))
        self.assertEqual(metadata.audio_codecs, ("aac",))
        self.assertEqual(metadata.pixel_formats, ("yuv420p",))
        self.assertEqual(metadata.video_stream_count, 1)
        self.assertEqual(metadata.audio_stream_count, 1)
        self.assertEqual((metadata.width, metadata.height), (160, 90))
        self.assertAlmostEqual(metadata.duration_seconds, 1, delta = 0.1)
        self.assertGreater(metadata.size_bytes, 0)
        self.assertTrue(metadata.has_fast_start)

    def test_prepare_video_preserves_compliant_input(self):
        result = video_file_utils.prepare_video(str(self.compliant_path))

        self.assertEqual(result, str(self.compliant_path))

    def test_prepare_video_repairs_fast_start(self):
        source_metadata = video_file_utils.inspect_video(str(self.no_fast_start_path))
        self.assertFalse(source_metadata.has_fast_start)

        result = video_file_utils.prepare_video(str(self.no_fast_start_path))
        self._temp_paths.append(result)

        self.assertNotEqual(result, str(self.no_fast_start_path))
        self.assertTrue(video_file_utils.video_meets_constraints(video_file_utils.inspect_video(result)))

    def test_prepare_video_converts_webm_codecs_and_container(self):
        source_metadata = video_file_utils.inspect_video(str(self.webm_path))
        self.assertEqual(source_metadata.container, "webm")
        self.assertEqual(source_metadata.video_codecs, ("vp9",))
        self.assertEqual(source_metadata.audio_codecs, ("opus",))

        result = video_file_utils.prepare_video(str(self.webm_path))
        self._temp_paths.append(result)
        metadata = video_file_utils.inspect_video(result)

        self.assertTrue(video_file_utils.video_meets_constraints(metadata))
        self.assertEqual(metadata.container, "mp4")
        self.assertEqual(metadata.video_codecs, ("h264",))
        self.assertEqual(metadata.audio_codecs, ("aac",))

    def test_prepare_video_reduces_dimensions_and_byte_size(self):
        result = video_file_utils.prepare_video(
            str(self.compliant_path),
            max_size_bytes = 100_000,
            max_width = 80,
            max_height = 46,
        )
        self._temp_paths.append(result)
        metadata = video_file_utils.inspect_video(result)

        self.assertNotEqual(result, str(self.compliant_path))
        self.assertLessEqual(metadata.width, 80)
        self.assertLessEqual(metadata.height, 46)
        self.assertLessEqual(metadata.size_bytes, 100_000)
        self.assertTrue(video_file_utils.video_meets_constraints(metadata, 100_000, 80, 46))

    def test_calculate_target_video_bitrate_reserves_audio_and_overhead(self):
        self.assertEqual(
            video_file_utils.calculate_target_video_bitrate(
                max_size_bytes = 1_000_000,
                duration_seconds = 10,
                has_audio = True,
            ),
            592_000,
        )
        self.assertEqual(
            video_file_utils.calculate_target_video_bitrate(
                max_size_bytes = 1_000_000,
                duration_seconds = 10,
                has_audio = False,
            ),
            720_000,
        )

    def test_calculate_target_video_bitrate_rejects_impossible_limit(self):
        with self.assertRaises(ExternalServiceError) as context:
            video_file_utils.calculate_target_video_bitrate(
                max_size_bytes = 100_000,
                duration_seconds = 10,
                has_audio = False,
            )

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_prepare_video_retries_with_lower_bitrate_and_resolution(self):
        run_process = subprocess.run
        outputs: list[Path] = []

        def oversized_first_passes(command, **kwargs):
            result = run_process(command, **kwargs)
            if Path(command[0]).name == "ffmpeg":
                output = Path(command[-1])
                outputs.append(output)
                if len(outputs) < 3:
                    with output.open("ab") as stream:
                        stream.write(b"0" * 100_001)
            return result

        # simulate encoder overshoot at the process boundary; inspection and retry logic stay real
        with patch.object(subprocess, "run", new = oversized_first_passes):
            result = video_file_utils.prepare_video(
                str(self.webm_path), max_size_bytes = 100_000, max_width = 160, max_height = 90,
            )

        self.assertEqual(len(outputs), 3)
        self.assertEqual(result, str(outputs[-1]))
        metadata = video_file_utils.inspect_video(result)
        self.assertLess(metadata.width, 160)
        self.assertTrue(video_file_utils.video_meets_constraints(metadata, 100_000, 160, 90))
        self.assertFalse(outputs[0].exists())
        self.assertFalse(outputs[1].exists())

    def test_run_process_reports_missing_runtime(self):
        with patch("features.videos.video_file_utils.shutil.which", return_value = None):
            with self.assertRaises(ConfigurationError) as context:
                video_file_utils._run_process(["ffprobe"], "ffprobe")

        self.assertEqual(context.exception.error_code, VIDEO_RUNTIME_MISSING)

    def test_run_process_reports_timeout(self):
        # timeout is a system process failure, not application behavior
        with patch.object(subprocess, "run", side_effect = subprocess.TimeoutExpired(["ffmpeg"], 300)):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils._run_process(["ffmpeg"], "ffmpeg")

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_run_process_reports_failed_command(self):
        with self.assertRaises(ExternalServiceError) as context:
            video_file_utils._run_process(["ffmpeg", "-definitely-invalid-option"], "ffmpeg")

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_inspect_video_rejects_empty_ffprobe_response(self):
        # exercise malformed external process output through the real parser
        with patch.object(subprocess, "run", return_value = stubs.external.process_result()):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils.inspect_video(str(self.compliant_path))

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_download_video_streams_to_temporary_file(self):
        content = b"first" * video_file_utils.DOWNLOAD_CHUNK_SIZE + b"second"
        self.http.responses["https://example.com/video.mp4"].append(stubs.external.http_response(content = content))

        result = video_file_utils.download_video("https://example.com/video.mp4")

        self.assertEqual(Path(result).read_bytes(), content)
        self.assertTrue(self.http.requests[0][1]["stream"])

    def test_download_video_removes_empty_temporary_file(self):
        self.http.responses["https://example.com/empty.mp4"].append(stubs.external.http_response(content = b""))

        with self.assertRaises(ExternalServiceError):
            video_file_utils.download_video("https://example.com/empty.mp4")

        self.assertEqual(list(self.root.iterdir()), [])

    def test_prepare_remote_video_files_removes_files_after_consumer_failure(self):
        self.http.responses["https://example.com/video.webm"].append(
            stubs.external.http_response(content = self.webm_path.read_bytes()),
        )

        with self.assertRaises(ExternalServiceError):
            with video_file_utils.prepare_remote_video_files("https://example.com/video.webm") as paths:
                self.assertTrue(Path(paths[0]).exists())
                self.assertTrue(Path(paths[1]).exists())
                self.assertNotEqual(paths[0], paths[1])
                raise ExternalServiceError("Delivery failed", VIDEO_PREPARATION_FAILED)

        self.assertEqual(list(self.root.iterdir()), [])

    def test_prepare_remote_video_files_keeps_paths_until_consumer_finishes(self):
        self.http.responses["https://example.com/video.webm"].append(
            stubs.external.http_response(content = self.webm_path.read_bytes()),
        )

        with video_file_utils.prepare_remote_video_files("https://example.com/video.webm") as paths:
            self.assertEqual(Path(paths[0]).read_bytes(), self.webm_path.read_bytes())
            self.assertGreater(Path(paths[1]).stat().st_size, 0)
            self.assertNotEqual(paths[0], paths[1])
            self.assertTrue(video_file_utils.video_meets_constraints(paths[2]))

        self.assertEqual(list(self.root.iterdir()), [])

    def test_prepare_video_removes_all_outputs_when_no_attempt_fits(self):
        run_process = subprocess.run
        attempts: list[Path] = []

        def oversized_output(command, **kwargs):
            result = run_process(command, **kwargs)
            if Path(command[0]).name == "ffmpeg":
                output = Path(command[-1])
                attempts.append(output)
                with output.open("ab") as stream:
                    stream.write(b"0" * 100_001)
            return result

        # force encoder overshoot while running real transcoding and metadata inspection
        with patch.object(subprocess, "run", new = oversized_output):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils.prepare_video(str(self.webm_path), max_size_bytes = 100_000)

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)
        self.assertEqual(len(attempts), len(video_file_utils.TRANSCODE_ATTEMPTS) + 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_video_preparation_slots_allow_two_concurrent_preparations(self):
        slots = video_file_utils.VIDEO_PREPARATION_SLOTS
        acquired = 0
        try:
            self.assertTrue(slots.acquire(blocking = False))
            acquired += 1
            self.assertTrue(slots.acquire(blocking = False))
            acquired += 1
            self.assertFalse(slots.acquire(blocking = False))
        finally:
            for _ in range(acquired):
                slots.release()

    def test_iso_media_layout_distinguishes_mov_and_fast_start(self):
        mov_path = self._temp_path(".mov")
        Path(mov_path).write_bytes(
            stubs.external.iso_media_box(b"ftyp", b"qt  " + b"\x00" * 4)
            + stubs.external.iso_media_box(b"moov")
            + stubs.external.iso_media_box(b"mdat"),
        )
        mp4_path = self._temp_path(".mp4")
        Path(mp4_path).write_bytes(
            stubs.external.iso_media_box(b"ftyp", b"isom" + b"\x00" * 4)
            + stubs.external.iso_media_box(b"mdat")
            + stubs.external.iso_media_box(b"moov"),
        )

        self.assertEqual(video_file_utils._inspect_iso_media_layout(mov_path), ("mov", True))
        self.assertEqual(video_file_utils._inspect_iso_media_layout(mp4_path), ("mp4", False))
