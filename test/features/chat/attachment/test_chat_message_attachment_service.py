import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from api.auth import verify_jwt_token, verify_public_resource_token
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_service import (
    ATTACHMENT_PUBLIC_READ_PURPOSE,
    ChatMessageAttachmentService,
)
from util.errors import ValidationError


class ChatMessageAttachmentServiceTest(unittest.TestCase):

    def setUp(self):
        self.di = SimpleNamespace(
            invoker_id = UUID(int = 1).hex,
            attachment_storage = Mock(),
            chat_message_attachment_repo = Mock(),
        )
        self.di.chat_message_attachment_repo.save.side_effect = lambda attachment: attachment
        self.service = ChatMessageAttachmentService(self.di)
        self.attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            message_id = "message-id",
        )

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_content_stores_content_and_saves_updated_metadata(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        content = b"\x89PNG\r\n\x1a\ncontent"

        result = self.service.save(self.attachment, content)

        self.di.attachment_storage.put.assert_called_once()
        stored_metadata, stored_content = self.di.attachment_storage.put.call_args.args
        self.assertEqual(stored_metadata.id, self.attachment.id)
        self.assertEqual(stored_metadata.mime_type, "image/png")
        self.assertEqual(stored_metadata.extension, "png")
        self.assertIsNone(stored_metadata.last_url)
        self.assertIsNone(stored_metadata.last_url_until)
        self.assertEqual(stored_content, content)

        self.di.chat_message_attachment_repo.save.assert_called_once_with(result)
        self.assertEqual(result.id, self.attachment.id)
        self.assertEqual(result.size, len(content))
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")
        self.assertIsNotNone(result.last_url)
        self.assertTrue(result.last_url.startswith("http://api.example/attachments/public/"))
        self.assertIsNotNone(result.last_url_until)

        token = result.last_url.rsplit("/", 1)[1]
        public_claims = verify_public_resource_token(token)
        jwt_claims = verify_jwt_token(token)
        self.assertEqual(public_claims.resource_id, self.attachment.id)
        self.assertEqual(public_claims.principal_id, self.di.invoker_id)
        self.assertEqual(public_claims.purpose, ATTACHMENT_PUBLIC_READ_PURPOSE)
        self.assertLessEqual(abs(result.last_url_until - jwt_claims["exp"]), 1)

    @patch("features.chat.attachment.chat_message_attachment_service.config")
    def test_save_with_content_preserves_explicit_file_type(self, mock_config):
        mock_config.public_api_base_url = "http://api.example"
        mock_config.attachment_public_token_ttl_seconds = 600
        attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
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
        attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
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

    def test_save_without_content_saves_existing_metadata(self):
        result = self.service.save(self.attachment)

        self.assertEqual(result, self.attachment)
        self.di.attachment_storage.put.assert_not_called()
        self.di.chat_message_attachment_repo.save.assert_called_once_with(self.attachment)
