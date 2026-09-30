import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from stubs import external

from features.images.image_size_utils import (
    calculate_image_size_category,
    convert_size_to_k,
    convert_size_to_mp,
    normalize_image_size_category,
    resize_file,
    resolve_closest_aspect_ratio,
)
from util.error_codes import INVALID_IMAGE_SIZE
from util.errors import ValidationError


class ImageSizeUtilsTest(unittest.TestCase):

    def _save(self, img: Image.Image, suffix: str, **kwargs) -> str:
        with tempfile.NamedTemporaryFile(suffix = suffix, delete = False) as f:
            path = f.name
        self.addCleanup(Path(path).unlink, missing_ok = True)
        img.save(path, **kwargs)
        return path

    # resize_file: early return

    def test_under_limit_returns_original_path(self):
        path = self._save(external.image_bitmap(size = (100, 100), noisy = True), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size
        result = resize_file(path, original_size + 1000)
        self.assertEqual(result, path)

    # resize_file: target band convergence

    def test_large_jpeg_resized_into_target_band(self):
        path = self._save(external.image_bitmap(size = (300, 300), noisy = True), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self.addCleanup(Path(result).unlink, missing_ok = True)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    def test_large_png_resized_into_target_band(self):
        path = self._save(external.image_bitmap(size = (300, 300), noisy = True), ".png", format = "PNG")
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self.addCleanup(Path(result).unlink, missing_ok = True)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    def test_large_webp_resized_into_target_band(self):
        path = self._save(external.image_bitmap(size = (300, 300), noisy = True), ".webp", format = "WEBP", quality = 90)
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self.addCleanup(Path(result).unlink, missing_ok = True)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    def test_resized_output_remains_readable_after_source_is_removed(self):
        path = self._save(external.image_bitmap(size = (300, 300), noisy = True), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size

        result = resize_file(path, original_size // 3)
        self.addCleanup(Path(result).unlink, missing_ok = True)
        Path(path).unlink()

        self.assertNotEqual(result, path)
        with Image.open(result) as image:
            image.verify()

    # resize_file: edge cases

    def test_min_dimension_guard_rejects_unresizable_image(self):
        path = self._save(external.image_bitmap(size = (100, 100), noisy = True), ".jpg", format = "JPEG", quality = 90)
        with self.assertRaises(ValidationError) as ctx:
            resize_file(path, 10)

        self.assertEqual(ctx.exception.error_code, INVALID_IMAGE_SIZE)

    def test_unreachable_size_limit_returns_best_effort(self):
        path = self._save(external.image_bitmap(size = (1024, 1024)), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size

        result = resize_file(path, 100)

        self.addCleanup(Path(result).unlink, missing_ok = True)
        self.assertNotEqual(result, path)
        self.assertLess(Path(result).stat().st_size, original_size)
        self.assertGreater(Path(result).stat().st_size, 100)
        with Image.open(result) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLess(image.width, 1024)
            self.assertEqual(image.width, image.height)
            image.verify()

    def test_non_image_over_limit_returns_original_path(self):
        with tempfile.NamedTemporaryFile(suffix = ".txt", delete = False) as f:
            path = f.name
            self.addCleanup(Path(path).unlink, missing_ok = True)
            f.write(b"this is plain text, not an image at all" * 10)
        result = resize_file(path, 10)
        self.assertEqual(result, path)

    # normalize_image_size_category

    def test_normalize_strips_spaces_and_lowercases(self):
        self.assertEqual(normalize_image_size_category("  2  K  "), "2k")

    def test_normalize_mb_to_k(self):
        self.assertEqual(normalize_image_size_category("4 MB"), "4k")

    def test_normalize_mp_to_k(self):
        self.assertEqual(normalize_image_size_category("8 MP"), "8k")

    def test_normalize_m_to_k(self):
        self.assertEqual(normalize_image_size_category("2 M"), "2k")

    def test_normalize_already_k_passthrough(self):
        self.assertEqual(normalize_image_size_category("12k"), "12k")

    def test_normalize_mixed_case(self):
        self.assertEqual(normalize_image_size_category("4Mp"), "4k")

    # convert_size_to_mp

    def test_convert_size_to_mp_from_k(self):
        self.assertEqual(convert_size_to_mp("1K"), "1 MP")
        self.assertEqual(convert_size_to_mp("2K"), "2 MP")
        self.assertEqual(convert_size_to_mp("4K"), "4 MP")

    def test_convert_size_to_mp_already_mp(self):
        self.assertEqual(convert_size_to_mp("2 MP"), "2 MP")

    def test_convert_size_to_mp_case_insensitive(self):
        self.assertEqual(convert_size_to_mp("2k"), "2 MP")
        self.assertEqual(convert_size_to_mp("4K"), "4 MP")

    def test_convert_size_to_mp_invalid_defaults_to_2mp(self):
        self.assertEqual(convert_size_to_mp("invalid"), "2 MP")

    # convert_size_to_k

    def test_convert_size_to_k_from_mp(self):
        self.assertEqual(convert_size_to_k("1 MP"), "1K")
        self.assertEqual(convert_size_to_k("2 MP"), "2K")
        self.assertEqual(convert_size_to_k("4 MP"), "4K")

    def test_convert_size_to_k_already_k(self):
        self.assertEqual(convert_size_to_k("2K"), "2K")

    def test_convert_size_to_k_case_insensitive(self):
        self.assertEqual(convert_size_to_k("2 mp"), "2K")
        self.assertEqual(convert_size_to_k("4k"), "4K")

    def test_convert_size_to_k_invalid_defaults_to_2k(self):
        self.assertEqual(convert_size_to_k("invalid"), "2K")

    def test_convert_size_to_k_uses_custom_fallback(self):
        self.assertEqual(convert_size_to_k("invalid", fallback = "1K"), "1K")

    # resolve_closest_aspect_ratio

    def test_resolve_closest_aspect_ratio_keeps_supported_ratio(self):
        result = resolve_closest_aspect_ratio(
            aspect_ratio = "2:3",
            supported_aspect_ratios = ("9:16", "2:3", "16:9"),
            default_aspect_ratio = "16:9",
        )

        self.assertEqual(result, "2:3")

    def test_resolve_closest_aspect_ratio_falls_back_to_closest_supported_ratio(self):
        result = resolve_closest_aspect_ratio(
            aspect_ratio = "8:5",
            supported_aspect_ratios = ("9:16", "16:9"),
            default_aspect_ratio = "16:9",
        )

        self.assertEqual(result, "16:9")

    def test_resolve_closest_aspect_ratio_falls_back_for_invalid_ratio(self):
        result = resolve_closest_aspect_ratio(
            aspect_ratio = "invalid",
            supported_aspect_ratios = ("9:16", "16:9"),
            default_aspect_ratio = "16:9",
        )

        self.assertEqual(result, "16:9")

    # calculate_image_size_category

    def test_calculate_1k_for_small_image(self):
        path = self._save(external.image_bitmap(size = (500, 500)), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(file_path = path), "1k")

    def test_calculate_1k_for_binary_stream(self):
        path = self._save(external.image_bitmap(size = (500, 500)), ".jpg", format = "JPEG")
        with Path(path).open("rb") as stream:
            self.assertEqual(calculate_image_size_category(file_contents = stream), "1k")

    def test_calculate_1k_for_non_seekable_binary_stream(self):
        with external.http_response(content = external.image_bytes(image_format = "JPEG")) as response:
            self.assertFalse(response.raw.seekable())
            self.assertEqual(calculate_image_size_category(file_contents = response.raw), "1k")

    def test_calculate_prefers_file_contents_over_file_path(self):
        path = self._save(external.image_bitmap(size = (500, 500)), ".jpg", format = "JPEG")
        with io.BytesIO(external.image_bytes(image_format = "JPEG", size = (1200, 1200))) as file_contents:
            result = calculate_image_size_category(file_path = path, file_contents = file_contents)

        self.assertEqual(result, "2k")

    def test_calculate_raises_when_no_input_is_supplied(self):
        with self.assertRaises(ValidationError) as ctx:
            calculate_image_size_category()

        self.assertEqual(ctx.exception.error_code, INVALID_IMAGE_SIZE)

    def test_calculate_2k_for_1_to_2_mp(self):
        path = self._save(external.image_bitmap(size = (1200, 1200)), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(file_path = path), "2k")

    def test_calculate_4k_for_2_to_4_mp(self):
        path = self._save(external.image_bitmap(size = (1800, 1800)), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(file_path = path), "4k")

    def test_calculate_8k_for_4_to_8_mp(self):
        path = self._save(external.image_bitmap(size = (2400, 2400)), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(file_path = path), "8k")

    def test_calculate_12k_for_8_to_14_mp(self):
        path = self._save(external.image_bitmap(size = (3000, 3000)), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(file_path = path), "12k")

    def test_calculate_raises_for_over_14_mp(self):
        path = self._save(external.image_bitmap(size = (3750, 3750)), ".jpg", format = "JPEG")
        with self.assertRaises(ValidationError) as ctx:
            calculate_image_size_category(file_path = path)
        self.assertEqual(ctx.exception.error_code, INVALID_IMAGE_SIZE)
