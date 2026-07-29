import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from features.videos import video_file_utils
from util.error_codes import VIDEO_PREPARATION_FAILED, VIDEO_RUNTIME_MISSING
from util.errors import ConfigurationError, ExternalServiceError


class VideoFileUtilsTest(unittest.TestCase):

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
        self._temp_paths: list[str] = []

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
        source = replace(
            video_file_utils.inspect_video(str(self.webm_path)),
            width = 160,
            height = 90,
            duration_seconds = 10,
            size_bytes = 2_000_000,
        )
        oversized = replace(
            video_file_utils.inspect_video(str(self.compliant_path)),
            size_bytes = 1_200_000,
        )
        fitting = replace(
            oversized,
            width = 80,
            height = 44,
            size_bytes = 900_000,
        )
        outputs = [self._temp_path() for _ in range(3)]

        with patch(
            "features.videos.video_file_utils.inspect_video",
            side_effect = [source, oversized, oversized, fitting],
        ), patch(
            "features.videos.video_file_utils._create_temp_path",
            side_effect = outputs,
        ), patch("features.videos.video_file_utils._transcode_video") as mock_transcode:
            result = video_file_utils.prepare_video(
                "source.webm",
                max_size_bytes = 1_000_000,
                max_width = 160,
                max_height = 90,
            )

        self.assertEqual(result, outputs[2])
        self.assertEqual(
            mock_transcode.call_args_list,
            [
                call(
                    input_path = "source.webm",
                    output_path = outputs[0],
                    width = 160,
                    height = 90,
                    video_bitrate = None,
                    has_audio = True,
                ),
                call(
                    input_path = "source.webm",
                    output_path = outputs[1],
                    width = 160,
                    height = 90,
                    video_bitrate = 592_000,
                    has_audio = True,
                ),
                call(
                    input_path = "source.webm",
                    output_path = outputs[2],
                    width = 120,
                    height = 66,
                    video_bitrate = 473_600,
                    has_audio = True,
                ),
            ],
        )
        self.assertFalse(Path(outputs[0]).exists())
        self.assertFalse(Path(outputs[1]).exists())
        self.assertTrue(Path(outputs[2]).exists())

    def test_run_process_reports_missing_runtime(self):
        with patch("features.videos.video_file_utils.shutil.which", return_value = None):
            with self.assertRaises(ConfigurationError) as context:
                video_file_utils._run_process(["ffprobe"], "ffprobe")

        self.assertEqual(context.exception.error_code, VIDEO_RUNTIME_MISSING)

    def test_run_process_reports_timeout(self):
        with patch("features.videos.video_file_utils.shutil.which", return_value = "/usr/bin/ffmpeg"), patch(
            "features.videos.video_file_utils.subprocess.run",
            side_effect = subprocess.TimeoutExpired(["ffmpeg"], 300),
        ):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils._run_process(["ffmpeg"], "ffmpeg")

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_run_process_reports_failed_command(self):
        result = subprocess.CompletedProcess(
            ["ffmpeg"],
            returncode = 1,
            stdout = "",
            stderr = "conversion failed",
        )

        with patch("features.videos.video_file_utils.shutil.which", return_value = "/usr/bin/ffmpeg"), patch(
            "features.videos.video_file_utils.subprocess.run",
            return_value = result,
        ):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils._run_process(["ffmpeg"], "ffmpeg")

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_inspect_video_rejects_empty_ffprobe_response(self):
        result = subprocess.CompletedProcess(["ffprobe"], returncode = 0, stdout = "", stderr = "")

        with patch("features.videos.video_file_utils._run_process", return_value = result):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils.inspect_video(str(self.compliant_path))

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)

    def test_download_video_streams_to_temporary_file(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"first", b"", b"second"]

        with patch("features.videos.video_file_utils.requests.get", return_value = response):
            result = video_file_utils.download_video("https://example.com/video.mp4")
        self._temp_paths.append(result)

        self.assertEqual(Path(result).read_bytes(), b"firstsecond")
        response.iter_content.assert_called_once_with(chunk_size = video_file_utils.DOWNLOAD_CHUNK_SIZE)

    def test_download_video_removes_empty_temporary_file(self):
        output_path = self._temp_path(".video")
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = []

        with patch("features.videos.video_file_utils._create_temp_path", return_value = output_path), patch(
            "features.videos.video_file_utils.requests.get",
            return_value = response,
        ):
            with self.assertRaises(ExternalServiceError):
                video_file_utils.download_video("https://example.com/empty.mp4")

        self.assertFalse(Path(output_path).exists())

    def test_prepare_remote_video_files_removes_files_after_consumer_failure(self):
        original_path = self._temp_path(".video")
        prepared_path = self._temp_path(".mp4")
        Path(original_path).write_bytes(b"original")
        Path(prepared_path).write_bytes(b"prepared")
        metadata = video_file_utils.inspect_video(str(self.compliant_path))

        with patch(
            "features.videos.video_file_utils.download_video",
            return_value = original_path,
        ) as mock_download, patch(
            "features.videos.video_file_utils.prepare_video",
            return_value = prepared_path,
        ) as mock_prepare, patch("features.videos.video_file_utils.inspect_video", return_value = metadata):
            with self.assertRaises(ExternalServiceError):
                with video_file_utils.prepare_remote_video_files("https://example.com/video.mp4") as paths:
                    self.assertTrue(Path(paths[0]).exists())
                    self.assertTrue(Path(paths[1]).exists())
                    raise ExternalServiceError("Delivery failed", VIDEO_PREPARATION_FAILED)

        mock_download.assert_called_once_with("https://example.com/video.mp4")
        mock_prepare.assert_called_once_with(
            original_path,
            max_size_bytes = None,
            max_width = None,
            max_height = None,
        )
        self.assertFalse(Path(original_path).exists())
        self.assertFalse(Path(prepared_path).exists())

    def test_prepare_video_removes_all_outputs_when_no_attempt_fits(self):
        source = replace(
            video_file_utils.inspect_video(str(self.webm_path)),
            duration_seconds = 10,
            size_bytes = 2_000_000,
        )
        oversized = replace(
            video_file_utils.inspect_video(str(self.compliant_path)),
            size_bytes = 1_200_000,
        )
        outputs = [self._temp_path() for _ in range(len(video_file_utils.TRANSCODE_ATTEMPTS) + 1)]

        with patch(
            "features.videos.video_file_utils.inspect_video",
            side_effect = [source, *[oversized] * len(outputs)],
        ), patch(
            "features.videos.video_file_utils._create_temp_path",
            side_effect = outputs,
        ), patch("features.videos.video_file_utils._transcode_video"):
            with self.assertRaises(ExternalServiceError) as context:
                video_file_utils.prepare_video(
                    "source.webm",
                    max_size_bytes = 1_000_000,
                )

        self.assertEqual(context.exception.error_code, VIDEO_PREPARATION_FAILED)
        self.assertTrue(all(not Path(output).exists() for output in outputs))

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
            self._box(b"ftyp", b"qt  " + b"\x00" * 4)
            + self._box(b"moov")
            + self._box(b"mdat"),
        )
        mp4_path = self._temp_path(".mp4")
        Path(mp4_path).write_bytes(
            self._box(b"ftyp", b"isom" + b"\x00" * 4)
            + self._box(b"mdat")
            + self._box(b"moov"),
        )

        self.assertEqual(video_file_utils._inspect_iso_media_layout(mov_path), ("mov", True))
        self.assertEqual(video_file_utils._inspect_iso_media_layout(mp4_path), ("mp4", False))

    @staticmethod
    def _box(box_type: bytes, payload: bytes = b"") -> bytes:
        return (8 + len(payload)).to_bytes(4, byteorder = "big") + box_type + payload
