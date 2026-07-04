import unittest
from unittest.mock import MagicMock
from uuid import UUID

import requests_mock

from features.chat.url_attachment_resolver import UrlAttachmentResolver
from util.config import config
from util.errors import ValidationError

CHAT_ID = UUID(int = 1)
IMAGE_URL = "https://example.com/photo.jpg"
PNG_URL = "https://example.com/image.png"
UNSUPPORTED_URL = "https://example.com/file.xyz"
NO_EXT_URL = "https://example.com/media"


class UrlAttachmentResolverTest(unittest.TestCase):

    def setUp(self):
        config.web_retries = 1
        config.web_retry_delay_s = 0
        config.web_timeout_s = 1
        self.mock_di = MagicMock()
        self.mock_di.invoker_chat_id = CHAT_ID.hex

    def _resolver(self, url: str) -> UrlAttachmentResolver:
        return UrlAttachmentResolver(url, self.mock_di)

    @requests_mock.Mocker()
    def test_mime_from_head(self, m: requests_mock.Mocker):
        m.head(IMAGE_URL, headers = {"Content-Type": "image/jpeg"}, status_code = 200)
        result = self._resolver(IMAGE_URL).execute()
        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.last_url, IMAGE_URL)
        self.assertTrue(result.id.startswith("url-"))
        self.assertEqual(result.chat_id, CHAT_ID)

    @requests_mock.Mocker()
    def test_message_id_uses_virtual_prefix(self, m: requests_mock.Mocker):
        m.head(PNG_URL, exc = ConnectionError("timeout"))
        result = self._resolver(PNG_URL).execute()
        self.assertEqual(result.message_id, f"virtual-{result.id}")

    @requests_mock.Mocker()
    def test_mime_from_extension_fallback_when_head_fails(self, m: requests_mock.Mocker):
        m.head(PNG_URL, exc = ConnectionError("timeout"))
        result = self._resolver(PNG_URL).execute()
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")

    @requests_mock.Mocker()
    def test_mime_from_extension_fallback_when_head_returns_no_content_type(self, m: requests_mock.Mocker):
        m.head(PNG_URL, headers = {}, status_code = 200)
        result = self._resolver(PNG_URL).execute()
        self.assertEqual(result.mime_type, "image/png")

    @requests_mock.Mocker()
    def test_mime_from_extension_fallback_when_head_returns_unsupported_content_type(self, m: requests_mock.Mocker):
        m.head(PNG_URL, headers = {"Content-Type": "application/octet-stream"}, status_code = 200)
        result = self._resolver(PNG_URL).execute()
        self.assertEqual(result.mime_type, "image/png")

    @requests_mock.Mocker()
    def test_unsupported_type_rejection(self, m: requests_mock.Mocker):
        m.head(UNSUPPORTED_URL, headers = {}, status_code = 200)
        with self.assertRaises(ValidationError):
            self._resolver(UNSUPPORTED_URL).execute()

    @requests_mock.Mocker()
    def test_no_extension_and_head_fails_raises_validation_error(self, m: requests_mock.Mocker):
        m.head(NO_EXT_URL, exc = ConnectionError("refused"))
        with self.assertRaises(ValidationError):
            self._resolver(NO_EXT_URL).execute()

    @requests_mock.Mocker()
    def test_head_content_type_with_charset_params_stripped(self, m: requests_mock.Mocker):
        m.head(PNG_URL, headers = {"Content-Type": "image/png; charset=utf-8"}, status_code = 200)
        result = self._resolver(PNG_URL).execute()
        self.assertEqual(result.mime_type, "image/png")

    @requests_mock.Mocker()
    def test_unknown_url_extension_does_not_override_head_content_type(self, m: requests_mock.Mocker):
        m.head(UNSUPPORTED_URL, headers = {"Content-Type": "image/png"}, status_code = 200)
        result = self._resolver(UNSUPPORTED_URL).execute()
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")

    @requests_mock.Mocker()
    def test_url_with_query_params_extension_parsed_correctly(self, m: requests_mock.Mocker):
        url_with_query = "https://example.com/photo.jpg?token=abc&size=large"
        m.head(url_with_query, exc = ConnectionError("timeout"))
        result = self._resolver(url_with_query).execute()
        self.assertEqual(result.mime_type, "image/jpeg")

    @requests_mock.Mocker()
    def test_deterministic_id_from_same_url(self, m: requests_mock.Mocker):
        m.head(PNG_URL, exc = ConnectionError("timeout"))
        result1 = self._resolver(PNG_URL).execute()
        result2 = self._resolver(PNG_URL).execute()
        self.assertEqual(result1.id, result2.id)
