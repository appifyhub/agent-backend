import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from features.images.image_size_utils import (
    calculate_image_size_category,
    normalize_image_size_category,
    resize_file,
)
from util.error_codes import INVALID_IMAGE_SIZE
from util.errors import ValidationError


def _noisy_image(width: int, height: int) -> Image.Image:
    random.seed(42)
    data = [
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        for _ in range(width * height)
    ]
    img = Image.new("RGB", (width, height))
    img.putdata(data)
    return img


def _blank_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color = (100, 150, 200))


class ImageSizeUtilsTest(unittest.TestCase):

    def setUp(self):
        self._temp_files: list[str] = []

    def tearDown(self):
        for path in self._temp_files:
            Path(path).unlink(missing_ok = True)

    def _save(self, img: Image.Image, suffix: str, **kwargs) -> str:
        with tempfile.NamedTemporaryFile(suffix = suffix, delete = False) as f:
            path = f.name
        img.save(path, **kwargs)
        self._temp_files.append(path)
        return path

    # resize_file: early return

    def test_under_limit_returns_original_path(self):
        path = self._save(_noisy_image(100, 100), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size
        result = resize_file(path, original_size + 1000)
        self.assertEqual(result, path)

    # resize_file: target band convergence

    def test_large_jpeg_resized_into_target_band(self):
        path = self._save(_noisy_image(300, 300), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self._temp_files.append(result)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    def test_large_png_resized_into_target_band(self):
        path = self._save(_noisy_image(300, 300), ".png", format = "PNG")
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self._temp_files.append(result)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    def test_large_webp_resized_into_target_band(self):
        path = self._save(_noisy_image(300, 300), ".webp", format = "WEBP", quality = 90)
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        result = resize_file(path, max_size)
        self._temp_files.append(result)
        result_size = Path(result).stat().st_size
        self.assertLessEqual(result_size, max_size)
        self.assertGreaterEqual(result_size, int(max_size * 0.90))

    # resize_file: edge cases

    def test_min_dimension_guard_handles_gracefully(self):
        path = self._save(_noisy_image(100, 100), ".jpg", format = "JPEG", quality = 90)
        try:
            result = resize_file(path, 10)
            self._temp_files.append(result)
            self.assertTrue(Path(result).exists())
        except ValidationError as e:
            self.assertEqual(e.error_code, INVALID_IMAGE_SIZE)

    @patch("features.images.image_size_utils.MAX_ITERATIONS", 1)
    def test_iteration_safety_cap_terminates_and_returns_best_effort(self):
        path = self._save(_noisy_image(300, 300), ".jpg", format = "JPEG", quality = 90)
        original_size = Path(path).stat().st_size
        max_size = original_size // 3
        try:
            result = resize_file(path, max_size)
            self._temp_files.append(result)
            self.assertTrue(Path(result).exists())
        except ValidationError as e:
            self.assertEqual(e.error_code, INVALID_IMAGE_SIZE)

    def test_non_image_over_limit_returns_original_path(self):
        with tempfile.NamedTemporaryFile(suffix = ".txt", delete = False) as f:
            path = f.name
            f.write(b"this is plain text, not an image at all" * 10)
        self._temp_files.append(path)
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

    # calculate_image_size_category

    def test_calculate_1k_for_small_image(self):
        path = self._save(_blank_image(500, 500), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(path), "1k")

    def test_calculate_2k_for_1_to_2_mp(self):
        path = self._save(_blank_image(1200, 1200), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(path), "2k")

    def test_calculate_4k_for_2_to_4_mp(self):
        path = self._save(_blank_image(1800, 1800), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(path), "4k")

    def test_calculate_8k_for_4_to_8_mp(self):
        path = self._save(_blank_image(2400, 2400), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(path), "8k")

    def test_calculate_12k_for_8_to_14_mp(self):
        path = self._save(_blank_image(3000, 3000), ".jpg", format = "JPEG")
        self.assertEqual(calculate_image_size_category(path), "12k")

    def test_calculate_raises_for_over_14_mp(self):
        path = self._save(_blank_image(3750, 3750), ".jpg", format = "JPEG")
        with self.assertRaises(ValidationError) as ctx:
            calculate_image_size_category(path)
        self.assertEqual(ctx.exception.error_code, INVALID_IMAGE_SIZE)
