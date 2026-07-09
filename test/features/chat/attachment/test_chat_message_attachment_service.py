import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from api.auth import verify_jwt_token, verify_public_attachment_token
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_service import ChatMessageAttachmentService, RemoteAttachmentContent
from util.errors import ExternalServiceError, NotFoundError, ValidationError


class ChatMessageAttachmentServiceTest(unittest.TestCase):

    def setUp(self):
        self.di = SimpleNamespace(
            invoker_id = UUID(int = 1).hex,
            invoker = SimpleNamespace(id = UUID(int = 1)),
            attachment_storage = Mock(),
            chat_message_attachment_repo = Mock(),
            require_invoker_chat = Mock(return_value = SimpleNamespace(chat_id = UUID(int = 2))),
        )
        self.di.chat_message_attachment_repo.save.side_effect = lambda attachment: attachment
        self.service = ChatMessageAttachmentService(self.di)
        self.attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = UUID(int = 1),
            message_id = "message-id",
        )

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_content_stores_content_and_saves_updated_metadata(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        mock_config.s3_bucket = "the-agent"
        content = b"\x89PNG\r\n\x1a\ncontent"
        expected_storage_uri = "s3://the-agent/chats/00000000-0000-0000-0000-000000000002/attachments/attachment-id.png"

        result = self.service.save(self.attachment, content)

        self.di.attachment_storage.put.assert_called_once()
        stored_metadata, stored_content = self.di.attachment_storage.put.call_args.args
        self.assertEqual(stored_metadata.id, self.attachment.id)
        self.assertEqual(stored_metadata.mime_type, "image/png")
        self.assertEqual(stored_metadata.extension, "png")
        self.assertEqual(stored_metadata.last_url, expected_storage_uri)
        self.assertIsNone(stored_metadata.last_url_until)
        self.assertEqual(stored_metadata.uploader_user_id, UUID(int = 1))
        self.assertEqual(stored_content, content)

        self.di.chat_message_attachment_repo.save.assert_called_once_with(result)
        self.assertEqual(result.id, self.attachment.id)
        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")
        self.assertEqual(result.last_url, expected_storage_uri)
        self.assertIsNone(result.last_url_until)
        self.assertEqual(result.uploader_user_id, UUID(int = 1))

        public_url = self.service.create_public_url(result)
        token = public_url.url.rsplit("/", 1)[1]
        public_claims = verify_public_attachment_token(token)
        jwt_claims = verify_jwt_token(token)
        self.assertEqual(public_claims.attachment_id, self.attachment.id)
        self.assertEqual(public_claims.chat_id, self.attachment.chat_id.hex)
        self.assertEqual(public_claims.issuer_user_id, self.di.invoker_id)
        self.assertLessEqual(abs(public_url.valid_until - jwt_claims["exp"]), 1)

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_content_preserves_explicit_file_type(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        mock_config.s3_bucket = "the-agent"
        attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = UUID(int = 1),
            message_id = "message-id",
            mime_type = "image/jpeg",
            extension = "jpg",
        )

        result = self.service.save(attachment, b"\x89PNG\r\n\x1a\ncontent")

        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.extension, "jpg")

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_content_uses_last_url_for_file_type_fallback(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        mock_config.s3_bucket = "the-agent"
        attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = UUID(int = 1),
            message_id = "message-id",
            last_url = "https://example.com/document.pdf?token=abc",
        )

        result = self.service.save(attachment, b"%PDF-1.4")

        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, "pdf")

    def test_save_with_content_rejects_empty_content(self):
        with self.assertRaises(ValidationError):
            self.service.save(self.attachment, b"")

        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_remote_url_fetches_content_and_stores_attachment(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.s3_bucket = "the-agent"
        content = b"%PDF-1.4"

        result = self.service.save(
            self.attachment,
            remote_url = "https://example.com/document.pdf",
            remote_url_fetcher = lambda _: RemoteAttachmentContent(
                content = content,
                response_mime_type = "application/pdf",
            ),
        )

        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, "pdf")
        self.assertEqual(result.last_url, f"s3://the-agent/{result.uri}")
        self.di.attachment_storage.put.assert_called_once()
        stored_metadata, stored_content = self.di.attachment_storage.put.call_args.args
        self.assertEqual(stored_metadata, result)
        self.assertEqual(stored_content, content)
        self.di.chat_message_attachment_repo.save.assert_called_once_with(result)

    def test_save_with_remote_url_rejects_missing_content(self):
        with self.assertRaises(ExternalServiceError):
            self.service.save(
                self.attachment,
                remote_url = "https://example.com/photo.png",
                remote_url_fetcher = lambda _: RemoteAttachmentContent(content = b""),
            )

        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_own_public_url_returns_existing_attachment(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        public_url = self.service.create_public_url(self.attachment)
        new_attachment = ChatMessageAttachment(
            id = "new-attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = UUID(int = 1),
        )
        self.di.chat_message_attachment_repo.get.return_value = self.attachment

        result = self.service.save(new_attachment, remote_url = public_url.url)

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_own_private_url_returns_existing_attachment(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        self.di.chat_message_attachment_repo.get.return_value = self.attachment

        result = self.service.save(
            self.attachment,
            remote_url = "http://api.example/attachments/private/attachment-id",
        )

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_own_storage_uri_returns_existing_attachment(self, mock_config):
        mock_config.s3_bucket = "the-agent"
        self.di.chat_message_attachment_repo.get.return_value = self.attachment

        result = self.service.save(
            self.attachment,
            remote_url = f"s3://the-agent/{self.attachment.uri}",
        )

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_own_storage_uri_strips_optional_extension(self, mock_config):
        mock_config.s3_bucket = "the-agent"
        stored_attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = UUID(int = 1),
            extension = "png",
        )
        self.di.chat_message_attachment_repo.get.return_value = self.attachment

        result = self.service.save(
            self.attachment,
            remote_url = f"s3://the-agent/{stored_attachment.uri}",
        )

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_not_called()

    def test_save_without_content_saves_existing_metadata(self):
        result = self.service.save(self.attachment)

        self.assertEqual(result, self.attachment)
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_called_once_with(self.attachment)

    def test_get_returns_attachment(self):
        self.di.chat_message_attachment_repo.get.return_value = self.attachment

        result = self.service.get("attachment-id")

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")

    def test_get_returns_attachment_instance(self):
        result = self.service.get(self.attachment)

        self.assertEqual(result, self.attachment)
        self.di.chat_message_attachment_repo.get.assert_not_called()

    def test_get_rejects_missing_attachment(self):
        self.di.chat_message_attachment_repo.get.return_value = None

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
        self.di.chat_message_attachment_repo.get.return_value = None

        with self.assertRaises(NotFoundError) as context:
            self.service.resolve_attachments(["missing"], [])

        self.assertIn("Attachment 'missing' not found", str(context.exception))

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_resolve_attachments_resolves_ids_and_urls(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.s3_bucket = "the-agent"
        mock_config.web_timeout_s = 5
        self.di.chat_message_attachment_repo.get.return_value = self.attachment
        self.di.require_invoker_chat = Mock(return_value = SimpleNamespace(chat_id = UUID(int = 2)))

        with patch("features.chat.attachment.chat_message_attachment_service.requests") as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"\x89PNG\r\n\x1a\ncontent"
            mock_response.headers = {"Content-Type": "image/png"}
            mock_requests.get.return_value = mock_response

            result = self.service.resolve_attachments(["attachment-id"], ["http://example.com/photo.png"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], self.attachment)
        self.assertEqual(result[1].mime_type, "image/png")
        self.assertEqual(result[1].extension, "png")
        self.di.attachment_storage.put.assert_called_once()

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_is_own_public_url_matches_public_api_base(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"

        self.assertTrue(self.service.is_own_public_url("http://api.example/attachments/public/token"))
        self.assertFalse(self.service.is_own_public_url("http://api.example/attachments/public/token/extra"))
        self.assertFalse(self.service.is_own_public_url("http://other.example/attachments/public/token"))
        self.assertFalse(self.service.is_own_public_url(None))

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_is_own_private_url_matches_private_api_base(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"

        self.assertTrue(self.service.is_own_private_url("http://api.example/attachments/private/attachment-id"))
        self.assertFalse(self.service.is_own_private_url("http://api.example/attachments/private/id/extra"))
        self.assertFalse(self.service.is_own_private_url("http://other.example/attachments/private/attachment-id"))
        self.assertFalse(self.service.is_own_private_url(None))

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_is_own_storage_uri_matches_configured_bucket(self, mock_config):
        mock_config.s3_bucket = "the-agent"

        self.assertTrue(self.service.is_own_storage_uri("s3://the-agent/chats/chat-id/attachments/attachment-id"))
        self.assertFalse(self.service.is_own_storage_uri("s3://other/chats/chat-id/attachments/attachment-id"))
        self.assertFalse(self.service.is_own_storage_uri(None))

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_create_public_url_does_not_persist_delivery_metadata(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600

        result = self.service.create_public_url(self.attachment)

        self.di.chat_message_attachment_repo.save.assert_not_called()
        self.assertTrue(result.url.startswith("http://api.example/attachments/public/"))
        self.assertIsNotNone(result.valid_until)

    @patch("features.chat.attachment.chat_message_attachment_service.log")
    def test_cleanup_old_attachments_deletes_rows_and_storage(self, _):
        from datetime import datetime
        cutoff = datetime(2026, 1, 1)
        self.di.chat_message_attachment_repo.delete_stale.return_value = [self.attachment]

        result = self.service.cleanup_old_attachments(cutoff)

        self.di.chat_message_attachment_repo.delete_stale.assert_called_once_with(cutoff)
        self.di.attachment_storage.delete.assert_called_once_with(self.attachment)
        self.assertEqual(result, 1)

    @patch("features.chat.attachment.chat_message_attachment_service.log")
    def test_cleanup_old_attachments_tolerates_storage_failures(self, _):
        from datetime import datetime
        cutoff = datetime(2026, 1, 1)
        self.di.chat_message_attachment_repo.delete_stale.return_value = [self.attachment]
        self.di.attachment_storage.delete.side_effect = RuntimeError("S3 down")

        result = self.service.cleanup_old_attachments(cutoff)

        self.assertEqual(result, 1)

    @patch("features.chat.attachment.chat_message_attachment_service.log")
    def test_cleanup_orphaned_attachments_deletes_rows_and_storage(self, _):
        from datetime import datetime
        cutoff = datetime(2026, 1, 1)
        self.di.chat_message_attachment_repo.delete_stale.return_value = [self.attachment]

        result = self.service.cleanup_orphaned_attachments(cutoff)

        self.di.chat_message_attachment_repo.delete_stale.assert_called_once_with(cutoff, only_orphans = True)
        self.di.attachment_storage.delete.assert_called_once_with(self.attachment)
        self.assertEqual(result, 1)

    @patch("features.chat.attachment.chat_message_attachment_service.log")
    def test_cleanup_orphaned_attachments_tolerates_storage_failures(self, _):
        from datetime import datetime
        cutoff = datetime(2026, 1, 1)
        self.di.chat_message_attachment_repo.delete_stale.return_value = [self.attachment]
        self.di.attachment_storage.delete.side_effect = RuntimeError("S3 down")

        result = self.service.cleanup_orphaned_attachments(cutoff)

        self.assertEqual(result, 1)
