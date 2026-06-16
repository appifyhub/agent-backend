import unittest
from uuid import uuid4

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.config.chat_config_repo import ChatConfigRepository


class ChatConfigRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatConfigRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_config_repo()

    def tearDown(self):
        self.sql.end_session()

    def _chat_config(
        self,
        external_id: str = "chat1",
        title: str = "Chat One",
        is_private: bool = True,
        chat_type: ChatConfigDB.ChatType = ChatConfigDB.ChatType.telegram,
    ) -> ChatConfig:
        return ChatConfig(
            external_id = external_id,
            language_iso_code = "en",
            language_name = "English",
            title = title,
            is_private = is_private,
            reply_chance_percent = 75,
            release_notifications = ChatConfigDB.ReleaseNotifications.minor,
            media_mode = ChatConfigDB.MediaMode.file,
            chat_type = chat_type,
        )

    def test_save_creates_chat_config(self):
        chat_config = self._chat_config()

        result = self.repo.save(chat_config)

        self.assertIsNotNone(result.chat_id)
        self.assertEqual(result.external_id, chat_config.external_id)
        self.assertEqual(result.language_iso_code, chat_config.language_iso_code)
        self.assertEqual(result.language_name, chat_config.language_name)
        self.assertEqual(result.title, chat_config.title)
        self.assertEqual(result.is_private, chat_config.is_private)
        self.assertEqual(result.reply_chance_percent, chat_config.reply_chance_percent)
        self.assertEqual(result.release_notifications, chat_config.release_notifications)
        self.assertEqual(result.media_mode, chat_config.media_mode)
        self.assertEqual(result.chat_type, chat_config.chat_type)

    def test_get_returns_saved_chat_config(self):
        created = self.repo.save(self._chat_config())

        result = self.repo.get(created.chat_id)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, created.chat_id)
        self.assertEqual(result.external_id, created.external_id)

    def test_get_returns_none_when_missing(self):
        result = self.repo.get(uuid4())

        self.assertIsNone(result)

    def test_get_all_returns_saved_chat_configs(self):
        first = self.repo.save(self._chat_config(external_id = "chat1"))
        second = self.repo.save(self._chat_config(
            external_id = "chat2",
            chat_type = ChatConfigDB.ChatType.background,
        ))

        results = self.repo.get_all()

        self.assertEqual({result.chat_id for result in results}, {first.chat_id, second.chat_id})

    def test_get_by_external_identifiers_returns_saved_chat_config(self):
        created = self.repo.save(self._chat_config(external_id = "chat1"))

        result = self.repo.get_by_external_identifiers(
            external_id = "chat1",
            chat_type = ChatConfigDB.ChatType.telegram,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, created.chat_id)

    def test_get_by_external_identifiers_returns_none_when_missing(self):
        result = self.repo.get_by_external_identifiers(
            external_id = "missing",
            chat_type = ChatConfigDB.ChatType.telegram,
        )

        self.assertIsNone(result)

    def test_save_updates_existing_chat_config(self):
        created = self.repo.save(self._chat_config())
        update = ChatConfig(
            chat_id = created.chat_id,
            external_id = "updated-chat",
            language_iso_code = "fr",
            language_name = "French",
            title = "Updated Chat",
            is_private = False,
            reply_chance_percent = 0,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.all,
            chat_type = ChatConfigDB.ChatType.background,
        )

        result = self.repo.save(update)

        self.assertEqual(result.chat_id, created.chat_id)
        self.assertEqual(result.external_id, update.external_id)
        self.assertEqual(result.language_iso_code, update.language_iso_code)
        self.assertEqual(result.language_name, update.language_name)
        self.assertEqual(result.title, update.title)
        self.assertEqual(result.is_private, update.is_private)
        self.assertEqual(result.reply_chance_percent, update.reply_chance_percent)
        self.assertEqual(result.release_notifications, update.release_notifications)
        self.assertEqual(result.media_mode, update.media_mode)
        self.assertEqual(result.chat_type, update.chat_type)

    def test_delete_removes_chat_config(self):
        created = self.repo.save(self._chat_config())

        result = self.repo.delete(created.chat_id)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, created.chat_id)
        self.assertIsNone(self.repo.get(created.chat_id))

    def test_delete_returns_none_when_missing(self):
        result = self.repo.delete(uuid4())

        self.assertIsNone(result)

    def test_save_remote_data_creates_private_chat_with_defaults(self):
        remote_data = ChatConfigRemoteData(
            external_id = "remote-chat",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "Remote Chat",
            language_iso_code = "en",
        )

        result = self.repo.save(remote_data)

        self.assertIsNotNone(result.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.language_iso_code, remote_data.language_iso_code)
        self.assertIsNone(result.language_name)
        self.assertEqual(result.title, remote_data.title)
        self.assertTrue(result.is_private)
        self.assertEqual(result.reply_chance_percent, 100)
        self.assertEqual(result.release_notifications, ChatConfigDB.ReleaseNotifications.major)
        self.assertEqual(result.media_mode, ChatConfigDB.MediaMode.photo)
        self.assertEqual(result.chat_type, remote_data.chat_type)

    def test_save_remote_data_creates_public_chat_with_release_notifications_none(self):
        remote_data = ChatConfigRemoteData(
            external_id = "public-chat",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "Public Chat",
            is_private = False,
        )

        result = self.repo.save(remote_data)

        self.assertFalse(result.is_private)
        self.assertEqual(result.release_notifications, ChatConfigDB.ReleaseNotifications.none)

    def test_save_remote_data_updates_existing_remote_fields_only(self):
        created = self.repo.save(self._chat_config(
            external_id = "remote-chat",
            title = "Old Title",
            is_private = True,
        ))
        remote_data = ChatConfigRemoteData(
            external_id = "remote-chat",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "New Title",
            is_private = False,
            language_iso_code = "fr",
        )

        result = self.repo.save(remote_data)

        self.assertEqual(result.chat_id, created.chat_id)
        self.assertEqual(result.external_id, created.external_id)
        self.assertEqual(result.language_iso_code, created.language_iso_code)
        self.assertEqual(result.language_name, created.language_name)
        self.assertEqual(result.title, remote_data.title)
        self.assertFalse(result.is_private)
        self.assertEqual(result.reply_chance_percent, created.reply_chance_percent)
        self.assertEqual(result.release_notifications, created.release_notifications)
        self.assertEqual(result.media_mode, created.media_mode)
        self.assertEqual(result.chat_type, created.chat_type)

    def test_save_remote_data_preserves_existing_fields_for_null_remote_values(self):
        created = self.repo.save(self._chat_config(
            external_id = "remote-chat",
            title = "Old Title",
            is_private = False,
        ))
        remote_data = ChatConfigRemoteData(
            external_id = "remote-chat",
            chat_type = ChatConfigDB.ChatType.telegram,
            language_iso_code = "fr",
        )

        result = self.repo.save(remote_data)

        self.assertEqual(result.chat_id, created.chat_id)
        self.assertEqual(result.language_iso_code, created.language_iso_code)
        self.assertEqual(result.title, created.title)
        self.assertEqual(result.is_private, created.is_private)
