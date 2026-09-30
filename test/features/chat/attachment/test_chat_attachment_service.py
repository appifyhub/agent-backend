import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import stubs
from fakes.fake_http_client import FakeHTTPClient
from util.di_utils import FakeInterceptor, di_for_tests

from api.auth import verify_jwt_token, verify_public_attachment_token
from di.di import DI
from features.chat.attachment.chat_attachment_repo import ChatAttachmentRepository
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.attachment.storage.attachment_storage import AttachmentStorage
from util.config import config
from util.errors import ExternalServiceError, NotFoundError, ValidationError


class ChatAttachmentServiceTest(unittest.TestCase):

    di: DI
    repo: ChatAttachmentRepository
    storage: AttachmentStorage
    service: ChatAttachmentService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.repo = self.di.chat_attachment_repo
        self.di.inject_invoker(stubs.domain.user())
        self.di.inject_invoker_chat(stubs.domain.chat_config())
        self.storage = self.di.attachment_storage
        self.service = self.di.chat_attachment_service

    def test_save_with_content_stores_content_and_saves_updated_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        content = b"\x89PNG\r\n\x1a\ncontent"

        result = self.service.save(attachment, content)

        stored_metadata = self.repo.get(result.id)
        with self.storage.open(result) as stream:
            stored_content = stream.read()
        self.assertEqual(stored_metadata.id, attachment.id)
        self.assertEqual(stored_metadata.mime_type, "image/png")
        self.assertEqual(stored_metadata.extension, "png")
        self.assertEqual(stored_metadata.uploader_user_id, self.di.invoker.id)
        self.assertEqual(stored_content, content)

        self.assertEqual(self.repo.get(result.id), result)
        self.assertEqual(result.id, attachment.id)
        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")
        self.assertTrue(self.storage.owns_uri(result.last_url))
        self.assertTrue(result.last_url.endswith(result.uri))
        self.assertEqual(result.uploader_user_id, self.di.invoker.id)

        public_url = self.service.create_public_url(result)
        token = public_url.url.rsplit("/", 1)[1]
        public_claims = verify_public_attachment_token(token)
        jwt_claims = verify_jwt_token(token)
        self.assertEqual(public_claims.attachment_id, attachment.id)
        self.assertEqual(public_claims.chat_id, attachment.chat_id.hex)
        self.assertEqual(public_claims.issuer_user_id, self.di.invoker_id)
        self.assertLessEqual(abs(public_url.valid_until - jwt_claims["exp"]), 1)

    def test_save_deletes_old_object_when_extension_changes(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = None,
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )
        attachment = replace(attachment, last_url = self.storage.put(attachment, b"old content"))
        content = b"\x89PNG\r\n\x1a\ncontent"

        result = self.service.save(attachment, content)

        self.assertEqual(result.extension, "png")
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        with self.storage.open(result) as stream:
            self.assertEqual(stream.read(), b"\x89PNG\r\n\x1a\ncontent")
        self.assertEqual(self.repo.get(result.id), result)

    def test_save_keeps_old_object_when_extension_unchanged(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = None,
            size = None,
            extension = "png",
            last_url = None,
            mime_type = None,
        )
        attachment = replace(attachment, last_url = self.storage.put(attachment, b"old content"))
        content = b"\x89PNG\r\n\x1a\ncontent"

        result = self.service.save(attachment, content)

        self.assertEqual(result.uri, attachment.uri)
        with self.storage.open(attachment) as stream:
            self.assertEqual(stream.read(), content)

    def test_save_with_content_preserves_explicit_file_type(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
        )

        result = self.service.save(attachment, b"\x89PNG\r\n\x1a\ncontent")

        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.extension, "jpg")

    def test_save_with_content_normalizes_parameterized_mime_type(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        attachment = replace(attachment, mime_type = "audio/ogg; codecs=opus")

        result = self.service.save(attachment, b"audio data")

        self.assertEqual(result.mime_type, "audio/ogg")
        self.assertEqual(result.extension, "oga")
        stored_metadata = self.repo.get(result.id)
        self.assertEqual(stored_metadata.mime_type, "audio/ogg")
        self.assertEqual(stored_metadata.extension, "oga")

    def test_save_with_content_uses_last_url_for_file_type_fallback(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = "https://example.com/document.pdf?token=abc",
            extension = None,
            mime_type = None,
        )

        result = self.service.save(attachment, b"%PDF-1.4")

        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, "pdf")

    def test_save_with_content_uses_remote_url_for_video_type_fallback(self):

        result = self.service.save(
            stubs.domain.chat_attachment(
                id = uuid4().hex[:8],
                external_id = None,
                message_id = None,
                size = None,
                last_url = None,
                extension = None,
                mime_type = None,
            ),
            content = b"video data",
            remote_url = "https://example.com/video.webm?token=abc",
        )

        self.assertEqual(result.mime_type, "video/webm")
        self.assertEqual(result.extension, "webm")

    def test_save_with_content_rejects_empty_content(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with self.assertRaises(ValidationError):
            self.service.save(attachment, b"")

        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [])

    def test_save_with_file_stores_path_and_saves_matching_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        content = b"\x89PNG\r\n\x1a\ncontent"

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source")
            source.write_bytes(content)

            result = self.service.save(
                attachment,
                file_path = source,
                remote_url = "https://example.com/photo.png",
            )

            self.assertEqual(source.read_bytes(), content)
            with self.storage.open(result) as stream:
                self.assertEqual(stream.read(), content)
            stored_metadata = self.repo.get(result.id)

        self.assertEqual(stored_metadata.mime_type, "image/png")
        self.assertEqual(stored_metadata.extension, "png")
        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")
        self.assertTrue(self.storage.owns_uri(result.last_url))
        self.assertEqual(self.repo.get(result.id), result)

    def test_save_with_file_uses_remote_url_for_video_type_fallback(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source")
            source.write_bytes(b"video data")

            result = self.service.save(
                attachment,
                file_path = source,
                remote_url = "https://example.com/video.webm?token=abc",
            )

        self.assertEqual(result.mime_type, "video/webm")
        self.assertEqual(result.extension, "webm")

    def test_save_with_file_path_api_and_remote_url_fetcher_stores_fetched_content(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        content = b"%PDF-1.4"
        result = self.service.save(
            attachment,
            remote_url = "https://example.com/document",
            remote_url_fetcher = lambda _: stubs.domain.remote_attachment_content(
                content = content,
                response_mime_type = "application/pdf",
            ),
        )

        stored_metadata = self.repo.get(result.id)
        with self.storage.open(result) as stream:
            stored_content = stream.read()
        self.assertEqual(stored_metadata.mime_type, "application/pdf")
        self.assertEqual(stored_metadata.extension, "pdf")
        self.assertEqual(stored_content, content)
        self.assertEqual(result.size, len(content))

    def test_save_with_file_rejects_missing_file(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("missing")

            with self.assertRaises(ValidationError):
                self.service.save(attachment, file_path = source)

        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [])

    def test_save_with_empty_file_saves_existing_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("empty")
            source.touch()

            result = self.service.save(attachment, file_path = source)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get(attachment.id), attachment)

    def test_save_with_file_deletes_old_object_when_extension_changes(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        attachment = replace(attachment, last_url = self.storage.put(attachment, b"old content"))

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source.png")
            source.write_bytes(b"\x89PNG\r\n\x1a\ncontent")

            result = self.service.save(attachment, file_path = source)

        self.assertEqual(result.extension, "png")
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        with self.storage.open(result) as stream:
            self.assertEqual(stream.read(), b"\x89PNG\r\n\x1a\ncontent")
        self.assertEqual(self.repo.get(result.id), result)

    def test_save_with_file_does_not_remove_source_when_storage_fails(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source.png")
            source.write_bytes(b"\x89PNG\r\n\x1a\ncontent")

            # the system copy operation supplies a storage failure without replacing owned code
            with (
                patch("shutil.copyfile", side_effect = OSError("Disk full")),
                self.assertRaises(OSError),
            ):
                self.service.save(attachment, file_path = source)

            self.assertTrue(source.exists())

        self.assertEqual(self.repo.get_all(), [])

    def test_save_with_no_file_and_own_public_url_returns_existing_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        public_url = self.service.create_public_url(attachment)
        new_attachment = replace(attachment, id = "new-attachment-id")
        self.repo.save(attachment)

        result = self.service.save(new_attachment, remote_url = public_url.url)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_with_empty_file_and_own_public_url_returns_existing_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        public_url = self.service.create_public_url(attachment)
        new_attachment = replace(attachment, id = "new-attachment-id")
        self.repo.save(attachment)

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("empty")
            source.touch()

            result = self.service.save(new_attachment, remote_url = public_url.url, file_path = source)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_without_file_path_saves_existing_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        result = self.service.save(attachment)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get(attachment.id), attachment)

    def test_save_with_remote_url_fetches_content_and_stores_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        content = b"%PDF-1.4"

        result = self.service.save(
            attachment,
            remote_url = "https://example.com/document.pdf",
            remote_url_fetcher = lambda _: stubs.domain.remote_attachment_content(
                content = content,
                response_mime_type = "application/pdf",
            ),
        )

        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, "pdf")
        self.assertTrue(self.storage.owns_uri(result.last_url))
        stored_metadata = self.repo.get(result.id)
        with self.storage.open(result) as stream:
            stored_content = stream.read()
        self.assertEqual(replace(stored_metadata, last_url = result.last_url), result)
        self.assertEqual(stored_content, content)
        self.assertEqual(self.repo.get(result.id), result)

    def test_save_with_remote_url_rejects_missing_content(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        with self.assertRaises(ExternalServiceError):
            self.service.save(
                attachment,
                remote_url = "https://example.com/photo.png",
                remote_url_fetcher = lambda _: stubs.domain.remote_attachment_content(content = b""),
            )

        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [])

    def test_save_with_own_public_url_returns_existing_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600
        public_url = self.service.create_public_url(attachment)
        new_attachment = stubs.domain.chat_attachment(
            id = "new-attachment-id",
            external_id = None,
            message_id = None,
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )
        self.repo.save(attachment)

        result = self.service.save(new_attachment, remote_url = public_url.url)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_with_own_private_url_returns_existing_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.repo.save(attachment)

        result = self.service.save(
            attachment,
            remote_url = "http://api.example/attachments/private/attachment-id",
        )

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_with_own_storage_uri_returns_existing_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.repo.save(attachment)

        uri = self.storage.put(attachment, b"original content")

        result = self.service.save(
            attachment,
            remote_url = uri,
        )

        self.assertEqual(result, attachment)
        with self.storage.open(attachment) as stream:
            self.assertEqual(stream.read(), b"original content")
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_with_own_storage_uri_strips_optional_extension(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        stored_attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = None,
            size = None,
            last_url = None,
            extension = "png",
            mime_type = None,
        )
        self.repo.save(attachment)

        uri = self.storage.put(stored_attachment, b"original content")

        result = self.service.save(
            attachment,
            remote_url = uri,
        )

        self.assertEqual(result, attachment)
        with self.storage.open(stored_attachment) as stream:
            self.assertEqual(stream.read(), b"original content")
        self.assertEqual(self.repo.get_all(), [attachment])

    def test_save_with_external_id_returns_existing_stored_attachment(self):
        stored_attachment = stubs.domain.chat_attachment(
            id = "stored-id",
            external_id = "ext-1",
            message_id = "m1",
            last_url = "s3://the-agent/chats/00000000-0000-0000-0000-000000000002/attachments/stored-id.jpg",
            size = 1024,
        )
        stored_attachment = replace(stored_attachment, last_url = self.storage.put(stored_attachment, b"original content"))
        self.repo.save(stored_attachment)
        new_attachment = stubs.domain.chat_attachment(
            id = uuid4().hex[:8],
            external_id = "ext-1",
            message_id = "m2",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        result = self.service.save(
            new_attachment,
            remote_url = "ext-1",
            remote_url_fetcher = lambda _: stubs.domain.remote_attachment_content(content = b"should-not-fetch"),
        )

        self.assertEqual(result, stored_attachment)
        with self.storage.open(stored_attachment) as stream:
            self.assertEqual(stream.read(), b"original content")
        self.assertEqual(self.repo.get_all(), [stored_attachment])

    def test_save_without_content_saves_existing_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        result = self.service.save(attachment)

        self.assertEqual(result, attachment)
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(self.repo.get(attachment.id), attachment)

    def test_get_returns_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.repo.save(attachment)

        result = self.service.get("attachment-id")

        self.assertEqual(result, attachment)

    def test_get_returns_attachment_instance(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        result = self.service.get(attachment)

        self.assertEqual(result, attachment)
        self.assertEqual(self.repo.get_all(), [])

    def test_get_rejects_missing_attachment(self):
        with self.assertRaises(NotFoundError) as context:
            self.service.get("missing")

        self.assertIn("Attachment 'missing' not found", str(context.exception))

    def test_resolve_attachments_rejects_empty_sources(self):
        with self.assertRaises(ValidationError) as context:
            self.service.resolve_attachments([], [])

        self.assertIn("No attachment IDs or URLs provided", str(context.exception))

    def test_resolve_attachments_rejects_empty_attachment_id(self):
        with self.assertRaises(ValidationError) as context:
            self.service.resolve_attachments([""], [])

        self.assertIn("Attachment ID cannot be empty", str(context.exception))

    def test_resolve_attachments_rejects_missing_attachment(self):
        with self.assertRaises(NotFoundError) as context:
            self.service.resolve_attachments(["missing"], [])

        self.assertIn("Attachment 'missing' not found", str(context.exception))

    def test_resolve_attachments_resolves_ids_and_urls(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "web_timeout_s", config.web_timeout_s)
        config.web_timeout_s = 5
        self.repo.save(attachment)
        http = cast(FakeHTTPClient, self.di.http_client())
        http.responses["http://example.com/photo.png"].append(stubs.external.http_response(
            content = b"\x89PNG\r\n\x1a\ncontent",
            headers = {"Content-Type": "image/png"},
        ))
        result = self.service.resolve_attachments(["attachment-id"], ["http://example.com/photo.png"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], attachment)
        self.assertEqual(result[1].mime_type, "image/png")
        self.assertEqual(result[1].extension, "png")
        self.assertEqual(self.repo.get(result[1].id), result[1])
        with self.storage.open(result[1]) as stream:
            self.assertEqual(stream.read(), b"\x89PNG\r\n\x1a\ncontent")

    def test_resolve_image_attachments_accepts_supported_mime_type_or_extension(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        attachments = [
            replace(attachment, mime_type = "image/png"),
            replace(attachment, id = "extension-only", extension = "webp"),
        ]

        for image in attachments:
            self.repo.save(image)

        result = self.service.resolve_image_attachments([image.id for image in attachments], None)

        self.assertEqual(result, attachments)

    def test_resolve_image_attachments_rejects_non_image(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        attachment = replace(attachment, mime_type = "video/mp4", extension = "mp4")

        self.repo.save(attachment)

        with self.assertRaises(ValidationError) as context:
            self.service.resolve_image_attachments(["attachment-id"], None)

        self.assertIn("Attachment 'attachment-id' is not a supported image", str(context.exception))

    def test_is_own_public_url_matches_public_api_base(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"

        self.assertTrue(self.service.is_own_public_url("http://api.example/attachments/public/token"))
        self.assertFalse(self.service.is_own_public_url("http://api.example/attachments/public/token/extra"))
        self.assertFalse(self.service.is_own_public_url("http://other.example/attachments/public/token"))
        self.assertFalse(self.service.is_own_public_url(None))

    def test_is_own_private_url_matches_private_api_base(self):
        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"

        self.assertTrue(self.service.is_own_private_url("http://api.example/attachments/private/attachment-id"))
        self.assertFalse(self.service.is_own_private_url("http://api.example/attachments/private/id/extra"))
        self.assertFalse(self.service.is_own_private_url("http://other.example/attachments/private/attachment-id"))
        self.assertFalse(self.service.is_own_private_url(None))

    def test_is_own_storage_uri_delegates_to_storage_backend(self):
        attachment = stubs.domain.chat_attachment()
        uri = self.storage.put(attachment, b"content")

        self.assertTrue(self.service.is_own_storage_uri(uri))
        self.assertFalse(self.service.is_own_storage_uri("other://locator"))

    def test_create_public_url_does_not_persist_delivery_metadata(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        self.addCleanup(setattr, config, "public_api_base_url", config.public_api_base_url)
        config.public_api_base_url = "http://api.example"
        self.addCleanup(setattr, config, "attachment_public_token_ttl_seconds", config.attachment_public_token_ttl_seconds)
        config.attachment_public_token_ttl_seconds = 600

        result = self.service.create_public_url(attachment)

        self.assertEqual(self.repo.get_all(), [])
        self.assertEqual(result.id, attachment.id)
        self.assertTrue(result.url.startswith("http://api.example/attachments/public/"))
        self.assertIsNotNone(result.valid_until)

    def test_create_public_url_returns_direct_cdn_url_when_storage_serves_public_urls(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = "https://cdn-id.ucarecd.net/uuid/attachment-id.png",
            extension = None,
            mime_type = None,
        )

        interceptor = FakeInterceptor()
        interceptor.register_factory(AttachmentStorage, lambda request: request.di.uploadcare_attachment_storage())
        with di_for_tests(interceptor = interceptor) as di:
            result = di.chat_attachment_service.create_public_url(attachment)
            self.assertEqual(di.chat_attachment_repo.get_all(), [])

        self.assertEqual(result.id, attachment.id)
        self.assertEqual(result.url, "https://cdn-id.ucarecd.net/uuid/attachment-id.png")
        self.assertIsNotNone(result.valid_until)

    def test_cleanup_old_attachments_deletes_rows_and_storage(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        cutoff = datetime(2026, 1, 1)
        self.repo.save(attachment)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = attachment.chat_id,
            message_id = attachment.message_id,
            ingestion_order = 1,
            sent_at = datetime(2025, 12, 31),
        ))
        self.storage.put(attachment, b"content")

        result = self.service.cleanup_old_attachments(cutoff)

        self.assertIsNone(self.repo.get(attachment.id))
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(result, 1)

    def test_cleanup_old_attachments_tolerates_storage_failures(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = "message-id",
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        cutoff = datetime(2026, 1, 1)
        self.repo.save(attachment)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = attachment.chat_id,
            message_id = attachment.message_id,
            ingestion_order = 1,
            sent_at = datetime(2025, 12, 31),
        ))
        self.storage.put(attachment, b"content")
        # filesystem failures exercise the service error path with the real local adapter
        with patch.object(Path, "unlink", side_effect = PermissionError("access denied")):
            result = self.service.cleanup_old_attachments(cutoff)

        with self.storage.open(attachment) as stream:
            self.assertEqual(stream.read(), b"content")
        self.assertIsNone(self.repo.get(attachment.id))

        self.assertEqual(result, 1)

    def test_cleanup_orphaned_attachments_deletes_rows_and_storage(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = None,
            created_at = datetime(2025, 12, 31),
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        cutoff = datetime(2026, 1, 1)
        self.repo.save(attachment)
        self.storage.put(attachment, b"content")

        result = self.service.cleanup_orphaned_attachments(cutoff)

        self.assertIsNone(self.repo.get(attachment.id))
        with self.assertRaises(FileNotFoundError):
            self.storage.open(attachment)
        self.assertEqual(result, 1)

    def test_cleanup_orphaned_attachments_tolerates_storage_failures(self):
        attachment = stubs.domain.chat_attachment(
            id = "attachment-id",
            external_id = None,
            message_id = None,
            created_at = datetime(2025, 12, 31),
            size = None,
            last_url = None,
            extension = None,
            mime_type = None,
        )

        cutoff = datetime(2026, 1, 1)
        self.repo.save(attachment)
        self.storage.put(attachment, b"content")
        # filesystem failures exercise the service error path with the real local adapter
        with patch.object(Path, "unlink", side_effect = PermissionError("access denied")):
            result = self.service.cleanup_orphaned_attachments(cutoff)

        with self.storage.open(attachment) as stream:
            self.assertEqual(stream.read(), b"content")
        self.assertIsNone(self.repo.get(attachment.id))

        self.assertEqual(result, 1)
