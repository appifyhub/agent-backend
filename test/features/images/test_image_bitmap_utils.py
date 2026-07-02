import tempfile
import unittest
from pathlib import Path

from PIL import Image

from features.images.image_bitmap_utils import (
    flatten_transparency_over_black,
    image_has_transparency,
)


def _blank_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color = (100, 150, 200))


class ImageBitmapUtilsTest(unittest.TestCase):

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

    def test_transparent_png_flattens_over_black(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(255, 0, 0, 0), (10, 20, 30, 255)])
        path = self._save(image, ".png", format = "PNG")

        self.assertTrue(image_has_transparency(path))
        result = flatten_transparency_over_black(path)
        self._temp_files.append(result)

        with Image.open(result) as flattened:
            self.assertEqual(flattened.mode, "RGB")
            self.assertEqual(flattened.getpixel((0, 0)), (0, 0, 0))
            self.assertEqual(flattened.getpixel((1, 0)), (10, 20, 30))
        self.assertFalse(image_has_transparency(result))

    def test_semi_transparent_png_blends_over_black(self):
        image = Image.new("RGBA", (1, 1), color = (255, 0, 0, 128))
        path = self._save(image, ".png", format = "PNG")

        result = flatten_transparency_over_black(path)
        self._temp_files.append(result)

        with Image.open(result) as flattened:
            red, green, blue = flattened.getpixel((0, 0))
            self.assertIn(red, [127, 128])
            self.assertEqual(green, 0)
            self.assertEqual(blue, 0)

    def test_opaque_image_returns_original_path_when_flattened(self):
        path = self._save(_blank_image(10, 10), ".png", format = "PNG")

        self.assertFalse(image_has_transparency(path))
        self.assertEqual(flatten_transparency_over_black(path), path)
