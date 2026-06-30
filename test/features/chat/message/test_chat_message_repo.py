import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.users.user import User


class ChatMessageRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatMessageRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_message_repo()

    def tearDown(self):
        self.sql.end_session()

    def _create_chat(self, external_id: str) -> ChatConfig:
        return self.sql.chat_config_repo().save(ChatConfig(
            external_id = external_id,
            chat_type = ChatConfigDB.ChatType.telegram,
        ))

    def _create_user(self, external_id: int):
        return self.sql.user_repo().save(User(
            full_name = f"User {external_id}",
            telegram_user_id = external_id,
            group = UserDB.Group.standard,
        ))

    def test_save_inserts_complete_message(self):
        chat = self._create_chat("chat1")
        author = self._create_user(1)
        message = ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message1",
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "Hello",
        )

        result = self.repo.save(message)

        self.assertEqual(result, message)

    def test_get_uses_composite_identity(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        first = self.repo.save(ChatMessage(chat_id = first_chat.chat_id, message_id = "same", text = "First"))
        second = self.repo.save(ChatMessage(chat_id = second_chat.chat_id, message_id = "same", text = "Second"))

        self.assertEqual(self.repo.get(first_chat.chat_id, "same"), first)
        self.assertEqual(self.repo.get(second_chat.chat_id, "same"), second)

    def test_get_returns_none_when_missing(self):
        chat = self._create_chat("chat1")

        self.assertIsNone(self.repo.get(chat.chat_id, "missing"))

    def test_get_all_applies_pagination(self):
        chat = self._create_chat("chat1")
        self.repo.save(ChatMessage(chat_id = chat.chat_id, message_id = "message1", text = "First"))
        self.repo.save(ChatMessage(chat_id = chat.chat_id, message_id = "message2", text = "Second"))

        result = self.repo.get_all(skip = 1, limit = 1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].message_id, "message2")

    def test_get_latest_by_chat_orders_and_paginates(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        base_time = datetime(2026, 1, 2, 12, 0, 0)
        for i in range(4):
            self.repo.save(ChatMessage(
                chat_id = first_chat.chat_id,
                message_id = f"message{i}",
                sent_at = base_time + timedelta(minutes = i),
                text = str(i),
            ))
        self.repo.save(ChatMessage(
            chat_id = second_chat.chat_id,
            message_id = "other",
            sent_at = base_time + timedelta(hours = 1),
            text = "Other",
        ))

        result = self.repo.get_latest_by_chat(first_chat.chat_id, skip = 1, limit = 2)

        self.assertEqual([message.message_id for message in result], ["message2", "message1"])

    def test_save_exactly_replaces_non_identity_fields_from_independent_snapshot(self):
        chat = self._create_chat("chat1")
        first_author = self._create_user(1)
        second_author = self._create_user(2)
        created = self.repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message1",
            author_id = first_author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "Original",
        ))
        original_snapshot = replace(created)
        replacement = replace(
            created,
            author_id = second_author.id,
            sent_at = datetime(2026, 1, 2, 13, 0, 0),
            text = "Replacement",
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)
        self.assertEqual(created, original_snapshot)
        self.assertNotEqual(result.author_id, original_snapshot.author_id)
        self.assertNotEqual(result.sent_at, original_snapshot.sent_at)
        self.assertNotEqual(result.text, original_snapshot.text)

    def test_save_can_clear_optional_author(self):
        chat = self._create_chat("chat1")
        author = self._create_user(1)
        created = self.repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message1",
            author_id = author.id,
            text = "Hello",
        ))

        result = self.repo.save(replace(created, author_id = None))

        self.assertIsNone(result.author_id)

    def test_delete_returns_deleted_message(self):
        chat = self._create_chat("chat1")
        created = self.repo.save(ChatMessage(chat_id = chat.chat_id, message_id = "message1", text = "Hello"))

        result = self.repo.delete(chat.chat_id, "message1")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(chat.chat_id, "message1"))

    def test_delete_returns_none_when_missing(self):
        chat = self._create_chat("chat1")

        self.assertIsNone(self.repo.delete(chat.chat_id, "missing"))

    def test_delete_older_than_uses_strict_cutoff(self):
        chat = self._create_chat("chat1")
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "old",
            sent_at = cutoff - timedelta(seconds = 1),
            text = "Old",
        ))
        self.repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "boundary",
            sent_at = cutoff,
            text = "Boundary",
        ))
        self.repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "new",
            sent_at = cutoff + timedelta(seconds = 1),
            text = "New",
        ))

        deleted_count = self.repo.delete_older_than(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(chat.chat_id, "old"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, "boundary"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, "new"))
