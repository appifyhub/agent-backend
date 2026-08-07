import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.uploadcare_attachment_storage import (
    UPLOADCARE_PUBLIC_URL_TTL_SECONDS,
    UploadcareAttachmentStorage,
)
from util.errors import ExternalServiceError


class RawResponse(io.BytesIO):

    decode_content = False


class FakeSecret:

    __value: str

    def __init__(self, value: str):
        self.__value = value

    def get_secret_value(self) -> str:
        return self.__value


class UploadcareAttachmentStorageTest(unittest.TestCase):

    def test_declares_public_delivery_capability(self):
        self.assertTrue(UploadcareAttachmentStorage.SERVES_PUBLIC_URLS)

    def test_can_be_used_requires_complete_config(self):
        with patch("features.chat.attachment.storage.uploadcare_attachment_storage.config", self.__config()):
            self.assertTrue(UploadcareAttachmentStorage.can_be_used())

        for missing_field in ["uploadcare_public_key", "uploadcare_private_key", "uploadcare_cdn_id"]:
            with self.subTest(missing_field = missing_field):
                with patch(
                    "features.chat.attachment.storage.uploadcare_attachment_storage.config",
                    self.__config(missing_field = missing_field),
                ):
                    self.assertFalse(UploadcareAttachmentStorage.can_be_used())

    def test_owns_uri_recognizes_cdn_locator(self):
        storage, _ = self.__storage()

        self.assertTrue(storage.owns_uri("https://cdn-id.ucarecd.net/uuid/attachment-id.txt"))
        self.assertFalse(storage.owns_uri("https://other.ucarecd.net/uuid/x"))
        self.assertFalse(storage.owns_uri("s3://the-agent/chats/x"))
        self.assertFalse(storage.owns_uri(None))
        self.assertFalse(storage.owns_uri(""))

    def test_put_uploads_and_returns_cdn_url(self):
        storage, client = self.__storage()
        stored_file = SimpleNamespace(cdn_url = "https://cdn-id.ucarecd.net/uuid/", filename = "attachment-id.txt")
        client.upload.return_value = stored_file

        result = storage.put(self.__metadata(extension = "txt"), b"content")

        self.assertEqual(result, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertTrue(client.upload.call_args.kwargs["store"])

    def test_put_file_streams_source_with_attachment_filename(self):
        storage, client = self.__storage()
        stored_file = SimpleNamespace(cdn_url = "https://cdn-id.ucarecd.net/uuid/", filename = "attachment-id.txt")
        observed: dict[str, object] = {}

        def upload(stream, store):
            observed["name"] = stream.name
            observed["content"] = stream.read()
            observed["store"] = store
            return stored_file

        client.upload.side_effect = upload
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source.txt")
            source.write_bytes(b"content")

            result = storage.put_file(self.__metadata(extension = "txt"), source)

            self.assertEqual(source.read_bytes(), b"content")

        self.assertEqual(result, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertEqual(observed["name"], "attachment-id.txt")
        self.assertEqual(observed["content"], b"content")
        self.assertTrue(observed["store"])

    def test_put_raises_on_upload_failure(self):
        storage, client = self.__storage()
        client.upload.side_effect = RuntimeError("boom")

        with self.assertRaises(ExternalServiceError):
            storage.put(self.__metadata(extension = "txt"), b"content")

    def test_put_raises_when_upload_returns_no_public_url(self):
        for stored_file in [
            SimpleNamespace(cdn_url = "", filename = "attachment-id.txt"),
            SimpleNamespace(cdn_url = "https://cdn-id.ucarecd.net/uuid/", filename = ""),
        ]:
            with self.subTest(stored_file = stored_file):
                storage, client = self.__storage()
                client.upload.return_value = stored_file

                with self.assertRaises(ExternalServiceError):
                    storage.put(self.__metadata(extension = "txt"), b"content")

    def test_open_fetches_cdn_bytes(self):
        storage, _ = self.__storage()
        metadata = self.__metadata(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")

        with patch("features.chat.attachment.storage.uploadcare_attachment_storage.requests") as requests_mock:
            response = SimpleNamespace(status_code = 200, raw = RawResponse(b"cdn bytes"), close = Mock())
            requests_mock.get.return_value = response

            with storage.open(metadata) as stream:
                self.assertEqual(stream.read(), b"cdn bytes")

            self.assertEqual(requests_mock.get.call_args.args[0], metadata.last_url)
            self.assertTrue(requests_mock.get.call_args.kwargs["stream"])
            response.close.assert_called_once_with()

    def test_open_raises_when_cdn_returns_no_body(self):
        storage, _ = self.__storage()
        metadata = self.__metadata(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")

        with patch("features.chat.attachment.storage.uploadcare_attachment_storage.requests") as requests_mock:
            response = SimpleNamespace(status_code = 200, raw = RawResponse(), close = Mock())
            requests_mock.get.return_value = response

            with self.assertRaises(ExternalServiceError):
                storage.open(metadata)

            response.close.assert_called_once_with()

    def test_delete_removes_file_by_cdn_url(self):
        storage, client = self.__storage()
        file_handle = Mock()
        client.file.return_value = file_handle
        metadata = self.__metadata(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")

        storage.delete(metadata)

        client.file.assert_called_once_with(metadata.last_url)
        file_handle.delete.assert_called_once_with()

    def test_public_attachment_returns_stored_cdn_url_and_ttl(self):
        storage, _ = self.__storage()
        metadata = self.__metadata(last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")

        min_valid_until = int((datetime.now() + timedelta(seconds = UPLOADCARE_PUBLIC_URL_TTL_SECONDS)).timestamp())
        result = storage.public_attachment_for(metadata)
        max_valid_until = int((datetime.now() + timedelta(seconds = UPLOADCARE_PUBLIC_URL_TTL_SECONDS)).timestamp())

        self.assertEqual(result.id, metadata.id)
        self.assertEqual(result.url, "https://cdn-id.ucarecd.net/uuid/attachment-id.txt")
        self.assertGreaterEqual(result.valid_until, min_valid_until)
        self.assertLessEqual(result.valid_until, max_valid_until)

    def __storage(self) -> tuple[UploadcareAttachmentStorage, Mock]:
        client = Mock()
        with patch("features.chat.attachment.storage.uploadcare_attachment_storage.config", self.__config()):
            with patch(
                "features.chat.attachment.storage.uploadcare_attachment_storage.Uploadcare",
                return_value = client,
            ):
                return UploadcareAttachmentStorage(), client

    def __config(self, missing_field: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            uploadcare_public_key = "" if missing_field == "uploadcare_public_key" else "public",
            uploadcare_private_key = FakeSecret("" if missing_field == "uploadcare_private_key" else "private"),
            uploadcare_cdn_id = "" if missing_field == "uploadcare_cdn_id" else "cdn-id",
            web_timeout_s = 10,
        )

    def __metadata(
        self,
        extension: str | None = None,
        last_url: str | None = None,
    ) -> ChatAttachment:
        return ChatAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
            extension = extension,
            last_url = last_url,
        )
