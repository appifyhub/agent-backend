import tempfile
import unittest
from pathlib import Path

from PIL import Image
from stubs import external

from features.images.image_bitmap_utils import (
    add_outgoing_png_background,
    image_has_transparency,
    visible_content_is_light,
)


class ImageBitmapUtilsTest(unittest.TestCase):

    def _save(self, image: Image.Image, suffix: str, **kwargs) -> str:
        with tempfile.NamedTemporaryFile(suffix = suffix, delete = False) as file:
            path = file.name
        self.addCleanup(Path(path).unlink, missing_ok = True)
        image.save(path, **kwargs)
        return path

    def test_transparent_png_gets_opaque_background(self):
        image = external.image_bitmap(size = (80, 60), color = (0, 0, 0, 0))
        image.paste((245, 245, 245, 255), (25, 15, 55, 45))
        path = self._save(image, ".png", format = "PNG")

        result = add_outgoing_png_background(path)

        self.addCleanup(Path(result).unlink, missing_ok = True)
        self.assertNotEqual(result, path)
        self.assertTrue(image_has_transparency(path))
        with Image.open(result) as prepared:
            self.assertEqual(prepared.format, "PNG")
            self.assertEqual(prepared.mode, "RGB")
            self.assertEqual(prepared.size, image.size)

    def test_opaque_png_and_jpeg_are_unchanged(self):
        png_path = self._save(external.image_bitmap(color = (255, 255, 255)), ".png", format = "PNG")
        jpeg_path = self._save(external.image_bitmap(color = (255, 255, 255)), ".jpg", format = "JPEG")

        self.assertEqual(add_outgoing_png_background(png_path), png_path)
        self.assertEqual(add_outgoing_png_background(jpeg_path), jpeg_path)
        self.assertFalse(image_has_transparency(png_path))

    def test_visible_content_brightness_ignores_transparent_padding(self):
        light = external.image_bitmap(size = (64, 64), color = (0, 0, 0, 0))
        light.paste((240, 240, 240, 255), (24, 24, 40, 40))
        dark = external.image_bitmap(size = (64, 64), color = (255, 255, 255, 0))
        dark.paste((10, 10, 10, 255), (24, 24, 40, 40))
        transparent = external.image_bitmap(size = (64, 64), color = (255, 255, 255, 0))

        self.assertTrue(visible_content_is_light(light))
        self.assertFalse(visible_content_is_light(dark))
        self.assertFalse(visible_content_is_light(transparent))
