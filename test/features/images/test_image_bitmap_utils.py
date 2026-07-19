import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from features.images.image_bitmap_utils import (
    add_outgoing_png_background,
    image_has_transparency,
    visible_content_is_light,
)


class ImageBitmapUtilsTest(unittest.TestCase):

    def setUp(self):
        self._temp_files: list[str] = []

    def tearDown(self):
        for path in self._temp_files:
            Path(path).unlink(missing_ok = True)

    def _save(self, image: Image.Image, suffix: str, **kwargs) -> str:
        with tempfile.NamedTemporaryFile(suffix = suffix, delete = False) as file:
            path = file.name
        image.save(path, **kwargs)
        self._temp_files.append(path)
        return path

    def test_transparent_png_gets_opaque_background(self):
        image = Image.new("RGBA", (80, 60), color = (0, 0, 0, 0))
        image.paste((245, 245, 245, 255), (25, 15, 55, 45))
        path = self._save(image, ".png", format = "PNG")

        with patch("features.images.image_bitmap_utils.random.shuffle"), \
                patch("features.images.image_bitmap_utils.random.uniform", return_value = 0):
            result = add_outgoing_png_background(path)

        self._temp_files.append(result)
        self.assertNotEqual(result, path)
        self.assertTrue(image_has_transparency(path))
        with Image.open(result) as prepared:
            self.assertEqual(prepared.format, "PNG")
            self.assertEqual(prepared.mode, "RGB")
            self.assertEqual(prepared.size, image.size)

    def test_opaque_png_and_jpeg_are_unchanged(self):
        png_path = self._save(Image.new("RGB", (20, 20), color = "white"), ".png", format = "PNG")
        jpeg_path = self._save(Image.new("RGB", (20, 20), color = "white"), ".jpg", format = "JPEG")

        self.assertEqual(add_outgoing_png_background(png_path), png_path)
        self.assertEqual(add_outgoing_png_background(jpeg_path), jpeg_path)
        self.assertFalse(image_has_transparency(png_path))

    def test_visible_content_brightness_ignores_transparent_padding(self):
        light = Image.new("RGBA", (64, 64), color = (0, 0, 0, 0))
        light.paste((240, 240, 240, 255), (24, 24, 40, 40))
        dark = Image.new("RGBA", (64, 64), color = (255, 255, 255, 0))
        dark.paste((10, 10, 10, 255), (24, 24, 40, 40))
        transparent = Image.new("RGBA", (64, 64), color = (255, 255, 255, 0))

        self.assertTrue(visible_content_is_light(light))
        self.assertFalse(visible_content_is_light(dark))
        self.assertFalse(visible_content_is_light(transparent))
