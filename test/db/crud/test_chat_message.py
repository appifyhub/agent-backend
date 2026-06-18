import unittest
from datetime import datetime, timedelta

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.chat_message import ChatMessageSave
from db.schema.user import UserSave
from features.chat.config.chat_config import ChatConfig


class ChatMessageCRUDTest(unittest.TestCase):

    sql: SQLUtil

    def setUp(self):
        self.sql = SQLUtil()

    def tearDown(self):
        self.sql.end_session()

    def test_create_chat_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_message_data = ChatMessageSave(
            chat_id = chat.chat_id,
            message_id = "msg1",
            author_id = user.id,
            sent_at = datetime.now(),
            text = "Hello, world!",
        )

        chat_message = self.sql.chat_message_crud().create(chat_message_data)

        self.assertIsNotNone(chat_message.chat_id, chat_message_data.chat_id)
        self.assertEqual(chat_message.message_id, chat_message_data.message_id)
        self.assertEqual(chat_message.author_id, chat_message_data.author_id)
        self.assertEqual(chat_message.sent_at, chat_message_data.sent_at)
        self.assertEqual(chat_message.text, chat_message_data.text)

    def test_get_chat_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_message_data = ChatMessageSave(
            chat_id = chat.chat_id,
            message_id = "msg1",
            author_id = user.id,
            sent_at = datetime.now(),
            text = "Hello, world!",
        )
        created_chat_message = self.sql.chat_message_crud().create(chat_message_data)

        fetched_chat_message = self.sql.chat_message_crud().get(
            created_chat_message.chat_id,
            created_chat_message.message_id,
        )

        self.assertEqual(fetched_chat_message.chat_id, created_chat_message.chat_id)
        self.assertEqual(fetched_chat_message.message_id, created_chat_message.message_id)
        self.assertEqual(fetched_chat_message.author_id, created_chat_message.author_id)

    def test_get_all_chat_messages(self):
        chat1 = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat2 = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat2", chat_type = ChatConfigDB.ChatType.background),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_messages = [
            self.sql.chat_message_crud().create(
                ChatMessageSave(chat_id = chat1.chat_id, message_id = "msg1", author_id = user.id, text = "no1"),
            ),
            self.sql.chat_message_crud().create(
                ChatMessageSave(chat_id = chat2.chat_id, message_id = "msg2", author_id = user.id, text = "no2"),
            ),
        ]

        fetched_chat_messages = self.sql.chat_message_crud().get_all()

        self.assertEqual(len(fetched_chat_messages), len(chat_messages))
        for i in range(len(chat_messages)):
            self.assertEqual(fetched_chat_messages[i].chat_id, chat_messages[i].chat_id)
            self.assertEqual(fetched_chat_messages[i].message_id, chat_messages[i].message_id)
            self.assertEqual(fetched_chat_messages[i].author_id, chat_messages[i].author_id)

    def test_get_latest_chat_messages(self):
        chat1 = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat2 = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat2", chat_type = ChatConfigDB.ChatType.background),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )

        base_time = datetime.now()
        chat1_messages = [
            self.sql.chat_message_crud().create(
                ChatMessageSave(
                    chat_id = chat1.chat_id,
                    message_id = f"msg{i}",
                    author_id = user.id,
                    text = f"Message {i} for chat1",
                    sent_at = base_time + timedelta(minutes = i),
                ),
            ) for i in range(1, 6)
        ]
        chat2_messages = [
            self.sql.chat_message_crud().create(
                ChatMessageSave(
                    chat_id = chat2.chat_id,
                    message_id = f"msg{i}",
                    author_id = user.id,
                    text = f"Message {i} for chat2",
                    sent_at = base_time + timedelta(minutes = i + 10),
                ),
            ) for i in range(1, 4)
        ]

        # fetching without pagination
        fetched_chat1_messages = self.sql.chat_message_crud().get_latest_chat_messages(chat1.chat_id)
        limited_chat1_messages = self.sql.chat_message_crud().get_latest_chat_messages(chat1.chat_id, limit = 3)
        self.assertEqual(len(fetched_chat1_messages), len(chat1_messages))
        self.assertEqual(len(limited_chat1_messages), 3)
        for i, message in enumerate(reversed(chat1_messages)):  # we expect latest messages first
            self.assertEqual(fetched_chat1_messages[i].chat_id, message.chat_id)
            self.assertEqual(fetched_chat1_messages[i].message_id, message.message_id)
            self.assertEqual(fetched_chat1_messages[i].text, message.text)
        for i, message in enumerate(reversed(chat1_messages[-3:])):  # last 3 messages, reversed
            self.assertEqual(limited_chat1_messages[i].chat_id, message.chat_id)
            self.assertEqual(limited_chat1_messages[i].message_id, message.message_id)
            self.assertEqual(limited_chat1_messages[i].text, message.text)

        # fetching with pagination
        paginated_chat1_messages = self.sql.chat_message_crud().get_latest_chat_messages(chat1.chat_id, skip = 2, limit = 2)
        fetched_chat2_messages = self.sql.chat_message_crud().get_latest_chat_messages(chat2.chat_id)
        self.assertEqual(len(paginated_chat1_messages), 2)
        self.assertEqual(len(fetched_chat2_messages), len(chat2_messages))
        for i, message in enumerate(reversed(chat1_messages[1:3])):  # messages 2 and 3, reversed
            self.assertEqual(paginated_chat1_messages[i].chat_id, message.chat_id)
            self.assertEqual(paginated_chat1_messages[i].message_id, message.message_id)
            self.assertEqual(paginated_chat1_messages[i].text, message.text)
        for i, message in enumerate(reversed(chat2_messages)):
            self.assertEqual(fetched_chat2_messages[i].chat_id, message.chat_id)
            self.assertEqual(fetched_chat2_messages[i].message_id, message.message_id)
            self.assertEqual(fetched_chat2_messages[i].text, message.text)

    def test_update_chat_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_message_data = ChatMessageSave(
            chat_id = chat.chat_id,
            message_id = "msg1",
            author_id = user.id,
            sent_at = datetime.now(),
            text = "Hello, world!",
        )
        created_chat_message = self.sql.chat_message_crud().create(chat_message_data)

        update_data = ChatMessageSave(
            chat_id = created_chat_message.chat_id,
            message_id = created_chat_message.message_id,
            text = "Updated! Hello, world!",
        )
        updated_chat_message = self.sql.chat_message_crud().update(update_data)

        self.assertIsNotNone(updated_chat_message.chat_id, created_chat_message.chat_id)
        self.assertEqual(updated_chat_message.message_id, created_chat_message.message_id)
        self.assertEqual(updated_chat_message.author_id, created_chat_message.author_id)
        self.assertEqual(updated_chat_message.sent_at, created_chat_message.sent_at)
        self.assertEqual(updated_chat_message.text, update_data.text)

    def test_save_chat_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_message_data = ChatMessageSave(
            chat_id = chat.chat_id,
            message_id = "msg1",
            author_id = user.id,
            sent_at = datetime.now(),
            text = "Hello, world!",
        )

        # First, save should create the record
        saved_chat_message = self.sql.chat_message_crud().save(chat_message_data)
        self.assertIsNotNone(saved_chat_message)
        self.assertIsNotNone(saved_chat_message.sent_at)
        self.assertEqual(saved_chat_message.chat_id, chat_message_data.chat_id)
        self.assertEqual(saved_chat_message.message_id, chat_message_data.message_id)
        self.assertEqual(saved_chat_message.author_id, chat_message_data.author_id)
        self.assertEqual(saved_chat_message.text, chat_message_data.text)

        # Now, save should update the existing record
        update_data = ChatMessageSave(
            chat_id = saved_chat_message.chat_id,
            message_id = saved_chat_message.message_id,
            author_id = saved_chat_message.author_id,
            sent_at = saved_chat_message.sent_at,
            text = "Updated text!",
        )
        updated_chat_message = self.sql.chat_message_crud().save(update_data)
        self.assertIsNotNone(updated_chat_message)
        self.assertEqual(updated_chat_message.chat_id, chat_message_data.chat_id)
        self.assertEqual(updated_chat_message.message_id, chat_message_data.message_id)
        self.assertEqual(updated_chat_message.sent_at, chat_message_data.sent_at)
        self.assertEqual(updated_chat_message.author_id, chat_message_data.author_id)
        self.assertEqual(updated_chat_message.text, update_data.text)

    def test_delete_chat_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        chat_message_data = ChatMessageSave(
            chat_id = chat.chat_id,
            message_id = "msg1",
            author_id = user.id,
            sent_at = datetime.now(),
            text = "Hello, world!",
        )
        created_chat_message = self.sql.chat_message_crud().create(chat_message_data)

        deleted_chat_message = self.sql.chat_message_crud().delete(
            created_chat_message.chat_id,
            created_chat_message.message_id,
        )

        self.assertEqual(deleted_chat_message.chat_id, created_chat_message.chat_id)
        self.assertEqual(deleted_chat_message.message_id, created_chat_message.message_id)
        self.assertIsNone(
            self.sql.chat_message_crud().get(created_chat_message.chat_id, created_chat_message.message_id),
        )

    def test_delete_older_than(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "test-user",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )
        old_message = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "old_msg",
                author_id = user.id,
                sent_at = datetime.now() - timedelta(days = 31),
                text = "Old message",
            ),
        )
        recent_message = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "recent_msg",
                author_id = user.id,
                sent_at = datetime.now(),
                text = "Recent message",
            ),
        )
        old_chat_id, old_message_id = old_message.chat_id, old_message.message_id
        recent_chat_id, recent_message_id = recent_message.chat_id, recent_message.message_id
        cutoff = datetime.now() - timedelta(days = 30)

        deleted_count = self.sql.chat_message_crud().delete_older_than(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.sql.chat_message_crud().get(old_chat_id, old_message_id))
        self.assertIsNotNone(self.sql.chat_message_crud().get(recent_chat_id, recent_message_id))
