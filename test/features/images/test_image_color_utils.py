import unittest

from features.images.image_color_utils import relative_luminance


class ImageColorUtilsTest(unittest.TestCase):

    def test_relative_luminance_extremes(self):
        self.assertEqual(relative_luminance((0, 0, 0)), 0)
        self.assertEqual(relative_luminance((255, 255, 255)), 1)

    def test_relative_luminance_weights_channels(self):
        self.assertAlmostEqual(relative_luminance((255, 0, 0)), 0.299)
        self.assertAlmostEqual(relative_luminance((0, 255, 0)), 0.587)
        self.assertAlmostEqual(relative_luminance((0, 0, 255)), 0.114)

    def test_relative_luminance_returns_normalized_value(self):
        self.assertAlmostEqual(relative_luminance((128, 128, 128)), 128 / 255)
