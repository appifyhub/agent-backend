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
