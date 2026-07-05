import unittest
from io import BytesIO

from PIL import Image

from features.chat.supported_files import (
    detect_image_format,
    is_supported_extension,
    is_supported_mime_type,
    resolve_file_type,
)


class SupportedFilesTest(unittest.TestCase):

    def test_resolve_file_type_keeps_existing_mime_type_and_extension(self):
        result = resolve_file_type(mime_type = "image/jpeg", extension = "png")

        self.assertEqual(result, ("image/jpeg", "png"))

    def test_resolve_file_type_resolves_mime_type_from_extension(self):
        result = resolve_file_type(extension = "PNG")

        self.assertEqual(result, ("image/png", "PNG"))

    def test_resolve_file_type_resolves_extension_from_mime_type(self):
        result = resolve_file_type(mime_type = "image/jpeg")

        self.assertEqual(result, ("image/jpeg", "jpg"))

    def test_resolve_file_type_keeps_unknown_extension(self):
        result = resolve_file_type(extension = "unknown")

        self.assertEqual(result, (None, "unknown"))

    def test_resolve_file_type_keeps_unknown_mime_type(self):
        result = resolve_file_type(mime_type = "application/x-custom")

        self.assertEqual(result, ("application/x-custom", None))

    def test_resolve_file_type_returns_none_pair_without_input(self):
        result = resolve_file_type()

        self.assertEqual(result, (None, None))

    def test_resolve_file_type_resolves_from_uri(self):
        result = resolve_file_type(uri = "https://example.com/files/photo.PNG?token=secret")

        self.assertEqual(result, ("image/png", "png"))

    def test_resolve_file_type_resolves_from_local_path(self):
        result = resolve_file_type(uri = "/tmp/uploads/photo.webp")

        self.assertEqual(result, ("image/webp", "webp"))

    def test_resolve_file_type_resolves_from_s3_uri(self):
        result = resolve_file_type(uri = "s3://the-agent/chats/chat-id/file.pdf")

        self.assertEqual(result, ("application/pdf", "pdf"))

    def test_resolve_file_type_resolves_from_content(self):
        result = resolve_file_type(content = b"\x89PNG\r\n\x1a\ncontent")

        self.assertEqual(result, ("image/png", "png"))

    def test_resolve_file_type_uses_content_before_uri(self):
        result = resolve_file_type(
            uri = "https://example.com/files/photo.jpg",
            content = b"\x89PNG\r\n\x1a\ncontent",
        )

        self.assertEqual(result, ("image/png", "png"))

    def test_resolve_file_type_uses_uri_when_mime_type_extension_is_unknown(self):
        result = resolve_file_type(mime_type = "application/x-custom", uri = "s3://bucket/file.png")

        self.assertEqual(result, ("application/x-custom", "png"))

    def test_resolve_file_type_ignores_uri_when_mime_type_resolves_extension(self):
        result = resolve_file_type(mime_type = "image/jpeg", uri = "https://example.com/file.png")

        self.assertEqual(result, ("image/jpeg", "jpg"))

    def test_resolve_file_type_ignores_uri_when_extension_is_present(self):
        result = resolve_file_type(extension = "jpg", uri = "https://example.com/file.png")

        self.assertEqual(result, ("image/jpeg", "jpg"))

    def test_is_supported_mime_type(self):
        self.assertTrue(is_supported_mime_type("image/png"))
        self.assertFalse(is_supported_mime_type("application/x-custom"))
        self.assertFalse(is_supported_mime_type(None))

    def test_is_supported_extension(self):
        self.assertTrue(is_supported_extension("png"))
        self.assertTrue(is_supported_extension("PNG"))
        self.assertFalse(is_supported_extension("unknown"))
        self.assertFalse(is_supported_extension(None))

    def test_detect_image_format(self):
        pattern = [
            "bbbbwwww",
            "bbbbwwww",
            "bbbbwwww",
            "bbbbwwww",
            "wwwwbbbb",
            "wwwwbbbb",
            "wwwwbbbb",
            "wwwwbbbb",
        ]
        image = Image.new("RGB", (8, 8))
        for y, row in enumerate(pattern):
            for x, pixel in enumerate(row):
                color = (0, 0, 0) if pixel == "b" else (255, 255, 255)
                image.putpixel((x, y), color)

        formats = {
            "PNG": "png",
            "JPEG": "jpeg",
            "GIF": "gif",
            "BMP": "bmp",
            "WEBP": "webp",
            "TIFF": "tiff",
        }
        for encoded_format, expected in formats.items():
            with self.subTest(encoded_format = encoded_format):
                output = BytesIO()
                image.save(output, format = encoded_format)
                self.assertEqual(detect_image_format(output.getvalue()), expected)

    def test_detect_image_format_returns_none_for_unknown_content(self):
        self.assertIsNone(detect_image_format(b"unknown content"))
