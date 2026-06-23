import unittest
from datetime import datetime
from uuid import UUID

from features.chat.message.chat_message import ChatMessage


class ChatMessageDomainTest(unittest.TestCase):

    def test_sent_at_defaults_to_construction_time(self):
        before = datetime.now()

        message = ChatMessage(
            chat_id = UUID(int = 1),
            message_id = "message1",
            text = "Hello",
        )

        after = datetime.now()
        self.assertGreaterEqual(message.sent_at, before)
        self.assertLessEqual(message.sent_at, after)
