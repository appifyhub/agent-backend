import unittest

from features.chat.supported_files import is_supported_extension, is_supported_mime_type, resolve_file_type


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
