import unittest
from uuid import UUID, uuid4

import stubs


class ChatAttachmentDomainTest(unittest.TestCase):

    def test_uri_uses_attachment_identity(self):
        attachment = stubs.domain.chat_attachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
            extension = None,
        )

        self.assertEqual(
            attachment.uri,
            "chats/11111111-1111-1111-1111-111111111111/attachments/attachment-id",
        )

    def test_uri_includes_extension_when_available(self):
        attachment = stubs.domain.chat_attachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            id = "attachment-id",
            extension = "png",
        )

        self.assertEqual(
            attachment.uri,
            "chats/11111111-1111-1111-1111-111111111111/attachments/attachment-id.png",
        )

    def test_uri_uses_random_attachment_id(self):
        attachment = stubs.domain.chat_attachment(
            id = uuid4().hex[:8],
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            extension = None,
        )

        self.assertEqual(
            attachment.uri,
            f"chats/11111111-1111-1111-1111-111111111111/attachments/{attachment.id}",
        )
