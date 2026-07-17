import unittest
from uuid import UUID

from features.chat.attachment.chat_attachment import ChatAttachment


class ChatAttachmentDomainTest(unittest.TestCase):

    def test_uri_uses_attachment_identity(self):
        attachment = ChatAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
        )

        self.assertEqual(
            attachment.uri,
            "chats/11111111-1111-1111-1111-111111111111/attachments/attachment-id",
        )

    def test_uri_includes_extension_when_available(self):
        attachment = ChatAttachment(
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
        attachment = ChatAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
        )

        self.assertEqual(
            attachment.uri,
            f"chats/11111111-1111-1111-1111-111111111111/attachments/{attachment.id}",
        )
