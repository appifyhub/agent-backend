import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from features.social_cards.brand import BRAND_GRADIENT_END, BRAND_GRADIENT_START
from features.social_cards.theme import ThemeColors, _contrast_text, _derive_gradient_end, _dominant_from_path, pick_theme


def _make_solid_png(path: Path, r: int, g: int, b: int, size: int = 16) -> Path:
    img = Image.new("RGB", (size, size), color = (r, g, b))
    img.save(path, format = "PNG")
    return path


class ThemePickerTest(unittest.TestCase):

    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_falls_back_to_brand_when_no_images(self):
        theme = pick_theme(None, [])
        self.assertEqual(theme.gradient_start, BRAND_GRADIENT_START)
        self.assertEqual(theme.gradient_end, BRAND_GRADIENT_END)
        self.assertEqual(theme.text_color, "#ffffff")

    def test_falls_back_to_media_when_no_profile(self):
        red_png = _make_solid_png(self.root / "red.png", 200, 10, 10)
        theme = pick_theme(None, [red_png])
        self.assertNotEqual(theme.gradient_start, BRAND_GRADIENT_START)

    def test_media_takes_priority_over_profile(self):
        blue_png = _make_solid_png(self.root / "blue.png", 10, 10, 200)
        red_png = _make_solid_png(self.root / "red.png", 200, 10, 10)
        theme_with_media = pick_theme(blue_png, [red_png])
        theme_profile_only = pick_theme(blue_png, [])
        self.assertNotEqual(theme_with_media.gradient_start, theme_profile_only.gradient_start)

    def test_returns_theme_colors_dataclass(self):
        theme = pick_theme(None, [])
        self.assertIsInstance(theme, ThemeColors)

    def test_all_grayscale_image_falls_back_gracefully(self):
        gray_png = _make_solid_png(self.root / "gray.png", 128, 128, 128)
        theme = pick_theme(gray_png, [])
        self.assertIsNotNone(theme.gradient_start)
        self.assertIsNotNone(theme.gradient_end)
        self.assertIn(theme.text_color, ["#000000", "#ffffff"])


class ContrastTextTest(unittest.TestCase):

    def test_dark_background_returns_white_text(self):
        self.assertEqual(_contrast_text((0, 0, 0)), "#ffffff")
        self.assertEqual(_contrast_text((20, 20, 20)), "#ffffff")
        self.assertEqual(_contrast_text((10, 10, 200)), "#ffffff")

    def test_light_background_returns_black_text(self):
        self.assertEqual(_contrast_text((255, 255, 255)), "#000000")
        self.assertEqual(_contrast_text((230, 230, 230)), "#000000")
        self.assertEqual(_contrast_text((255, 240, 200)), "#000000")


class GradientDerivationTest(unittest.TestCase):

    def test_returns_different_color_from_input(self):
        rgb = (100, 50, 200)
        result = _derive_gradient_end(rgb)
        self.assertNotEqual(result, rgb)

    def test_result_is_valid_rgb(self):
        for rgb in [(0, 0, 0), (255, 255, 255), (100, 150, 200)]:
            r, g, b = _derive_gradient_end(rgb)
            self.assertGreaterEqual(r, 0)
            self.assertLessEqual(r, 255)
            self.assertGreaterEqual(g, 0)
            self.assertLessEqual(g, 255)
            self.assertGreaterEqual(b, 0)
            self.assertLessEqual(b, 255)


class DominantColorTest(unittest.TestCase):

    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_returns_none_for_missing_path(self):
        self.assertIsNone(_dominant_from_path(None))
        self.assertIsNone(_dominant_from_path(self.root / "missing.png"))

    def test_returns_tuple_for_valid_image(self):
        png = _make_solid_png(self.root / "red.png", 200, 50, 50)
        result = _dominant_from_path(png)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_returns_none_for_invalid_file(self):
        path = self.root / "invalid.png"
        path.write_bytes(b"not an image")
        self.assertIsNone(_dominant_from_path(path))
