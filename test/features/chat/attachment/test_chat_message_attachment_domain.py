import unittest
from datetime import datetime, timedelta
from uuid import UUID

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment


class ChatMessageAttachmentDomainTest(unittest.TestCase):

    def _attachment(
        self,
        last_url: str | None,
        last_url_until: int | None,
    ) -> ChatMessageAttachment:
        return ChatMessageAttachment(
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            message_id = "message1",
            last_url = last_url,
            last_url_until = last_url_until,
        )

    def test_has_stale_data_when_url_is_missing(self):
        attachment = self._attachment(
            last_url = None,
            last_url_until = int((datetime.now() + timedelta(hours = 1)).timestamp()),
        )

        self.assertTrue(attachment.has_stale_data)

    def test_has_stale_data_when_url_is_expired(self):
        attachment = self._attachment(
            last_url = "https://example.com/file",
            last_url_until = int((datetime.now() - timedelta(seconds = 1)).timestamp()),
        )

        self.assertTrue(attachment.has_stale_data)

    def test_has_fresh_data_when_url_expiration_is_in_the_future(self):
        attachment = self._attachment(
            last_url = "https://example.com/file",
            last_url_until = int((datetime.now() + timedelta(hours = 1)).timestamp()),
        )

        self.assertFalse(attachment.has_stale_data)

    def test_uri_uses_attachment_identity(self):
        attachment = ChatMessageAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
        )

        self.assertEqual(
            attachment.uri,
            "chats/11111111-1111-1111-1111-111111111111/attachments/attachment-id",
        )

    def test_uri_includes_extension_when_available(self):
        attachment = ChatMessageAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
            extension = "png",
        )

        self.assertEqual(
            attachment.uri,
            "chats/11111111-1111-1111-1111-111111111111/attachments/attachment-id.png",
        )

    def test_uri_uses_generated_attachment_id(self):
        attachment = ChatMessageAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
        )

        self.assertEqual(
            attachment.uri,
            f"chats/11111111-1111-1111-1111-111111111111/attachments/{attachment.id}",
        )
