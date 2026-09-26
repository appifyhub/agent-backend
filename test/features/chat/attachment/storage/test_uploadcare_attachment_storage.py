from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fakes.http_client import FakeHTTPClient
from fakes.uploadcare_client import FakeUploadcareClient
from pydantic import SecretStr
from pyuploadcare import Uploadcare
from requests import ConnectionError
from stubs import domain, external
from util.di import FakeInterceptor, di_for_tests

from features.chat.attachment.storage.uploadcare_attachment_storage import (
    UPLOADCARE_PUBLIC_URL_TTL_SECONDS,
    UploadcareAttachmentStorage,
)
from util.config import config
from util.error_codes import ATTACHMENT_STORAGE_FAILED
from util.errors import ExternalServiceError
from util.http_client import HTTPClient


class UploadcareAttachmentStorageTest(TestCase):

    def setUp(self):
        for name, value in {
            "uploadcare_public_key": "public",
            "uploadcare_private_key": SecretStr("private"),
            "uploadcare_cdn_id": "cdn-id",
            "web_timeout_s": 10,
        }.items():
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)
        self.client = FakeUploadcareClient()
        self.http = FakeHTTPClient()
        interceptor = FakeInterceptor()
        interceptor.register(Uploadcare, self.client)
        interceptor.register(HTTPClient, self.http)
        self.di = self.enterContext(di_for_tests(interceptor = interceptor))
        self.storage = self.di.uploadcare_attachment_storage()

    def test_declares_public_delivery_capability(self):
        self.assertTrue(UploadcareAttachmentStorage.SERVES_PUBLIC_URLS)

    def test_can_be_used_requires_complete_config(self):
        self.assertTrue(UploadcareAttachmentStorage.can_be_used())
        for name in ("uploadcare_public_key", "uploadcare_private_key", "uploadcare_cdn_id"):
            with self.subTest(missing_field = name):
                previous = getattr(config, name)
                try:
                    setattr(config, name, SecretStr("") if isinstance(previous, SecretStr) else "")
                    self.assertFalse(UploadcareAttachmentStorage.can_be_used())
                finally:
                    setattr(config, name, previous)

    def test_owns_uri_recognizes_cdn_locator(self):
        self.assertTrue(self.storage.owns_uri("https://cdn-id.ucarecd.net/uuid/attachment-id.txt"))
        self.assertFalse(self.storage.owns_uri("https://other.ucarecd.net/uuid/x"))
        self.assertFalse(self.storage.owns_uri("s3://the-agent/chats/x"))
        self.assertFalse(self.storage.owns_uri(None))
        self.assertFalse(self.storage.owns_uri(""))

    def test_put_uploads_and_returns_cdn_url(self):
        self.client.upload_results.append(external.uploadcare_file())

        result = self.storage.put(domain.chat_attachment(id = "attachment-id", extension = "txt"), b"content")

        self.assertEqual(result, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertEqual(self.client.uploads, [("attachment-id.txt", b"content", True)])
        self.assertTrue(self.client.upload_streams[0].closed)

    def test_put_file_streams_source_with_attachment_filename(self):
        self.client.upload_results.append(external.uploadcare_file())

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source.txt")
            source.write_bytes(b"content")

            result = self.storage.put_file(domain.chat_attachment(id = "attachment-id", extension = "txt"), source)

            self.assertEqual(source.read_bytes(), b"content")

        self.assertEqual(result, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertEqual(self.client.uploads, [("attachment-id.txt", b"content", True)])
        self.assertTrue(self.client.upload_streams[0].closed)

    def test_put_raises_on_upload_failure(self):
        failure = ConnectionError("upload failed")
        self.client.upload_results.append(failure)

        with self.assertRaises(ExternalServiceError) as raised:
            self.storage.put(domain.chat_attachment(id = "attachment-id", extension = "txt"), b"content")

        self.assertIs(raised.exception.__cause__, failure)
        self.assertTrue(self.client.upload_streams[0].closed)

    def test_put_raises_when_upload_returns_no_public_url(self):
        for stored_file in (
            external.uploadcare_file(cdn_url = ""),
            external.uploadcare_file(filename = ""),
            None,
        ):
            with self.subTest(stored_file = stored_file):
                self.client.upload_results.append(stored_file)
                with self.assertRaisesRegex(ExternalServiceError, "returned no public URL"):
                    self.storage.put(domain.chat_attachment(id = "attachment-id", extension = "txt"), b"content")
                self.assertTrue(self.client.upload_streams[-1].closed)

    def test_open_fetches_cdn_bytes(self):
        metadata = domain.chat_attachment(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        response = external.http_response(content = b"cdn bytes", url = metadata.last_url)
        self.http.responses[metadata.last_url].append(response)

        with self.storage.open(metadata) as stream:
            self.assertEqual(stream.read(), b"cdn bytes")

        self.assertEqual(self.http.requests, [(metadata.last_url, {"timeout": 40, "stream": True})])
        self.assertTrue(response.raw.decode_content)
        self.assertTrue(response.raw.closed)

    def test_open_raises_when_cdn_returns_no_body(self):
        metadata = domain.chat_attachment(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        response = external.http_response(content = b"", url = metadata.last_url)
        self.http.responses[metadata.last_url].append(response)

        with self.assertRaisesRegex(ExternalServiceError, "returned no body"):
            self.storage.open(metadata)

        self.assertTrue(response.raw.closed)

    def test_open_closes_unsuccessful_http_response(self):
        metadata = domain.chat_attachment()
        response = external.http_response(status_code = 404)
        self.http.responses[metadata.last_url].append(response)

        with self.assertRaisesRegex(ExternalServiceError, "returned no body"):
            self.storage.open(metadata)

        self.assertTrue(response.raw.closed)

    def test_open_wraps_transport_failure(self):
        metadata = domain.chat_attachment()
        failure = ConnectionError("read failed")
        self.http.responses[metadata.last_url].append(failure)

        with self.assertRaises(ExternalServiceError) as raised:
            self.storage.open(metadata)

        self.assertIs(raised.exception.__cause__, failure)

    def test_open_fails_when_fake_has_no_response(self):
        with self.assertRaises(ExternalServiceError) as raised:
            self.storage.open(domain.chat_attachment())

        self.assertIn("No HTTP response configured", str(raised.exception.__cause__))

    def test_delete_removes_file_by_cdn_url(self):
        metadata = domain.chat_attachment(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        stored_file = external.uploadcare_file()
        self.client.files[metadata.last_url] = stored_file

        self.storage.delete(metadata)

        self.assertEqual(self.client.requested_files, [metadata.last_url])
        self.assertTrue(stored_file.deleted)

    def test_delete_wraps_provider_failure(self):
        metadata = domain.chat_attachment()
        stored_file = external.uploadcare_file()
        failure = ExternalServiceError("provider unavailable", ATTACHMENT_STORAGE_FAILED)
        stored_file.delete_error = failure
        self.client.files[metadata.last_url] = stored_file

        with self.assertRaises(ExternalServiceError) as raised:
            self.storage.delete(metadata)

        self.assertIs(raised.exception.__cause__, failure)
        self.assertFalse(stored_file.deleted)

    def test_public_attachment_returns_stored_cdn_url_and_ttl(self):
        metadata = domain.chat_attachment(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")

        min_valid_until = int((datetime.now() + timedelta(seconds = UPLOADCARE_PUBLIC_URL_TTL_SECONDS)).timestamp())
        result = self.storage.public_attachment_for(metadata)
        max_valid_until = int((datetime.now() + timedelta(seconds = UPLOADCARE_PUBLIC_URL_TTL_SECONDS)).timestamp())

        self.assertEqual(result.id, metadata.id)
        self.assertEqual(result.url, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertGreaterEqual(result.valid_until, min_valid_until)
        self.assertLessEqual(result.valid_until, max_valid_until)
