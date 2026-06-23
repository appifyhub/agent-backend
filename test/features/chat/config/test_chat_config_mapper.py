import unittest
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData


class ChatConfigMapperTest(unittest.TestCase):

    chat_id: UUID
    db_model: ChatConfigDB
    domain_model: ChatConfig

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.db_model = ChatConfigDB(
            chat_id = self.chat_id,
            external_id = "chat1",
            language_iso_code = "en",
            language_name = "English",
            title = "Chat One",
            is_private = False,
            reply_chance_percent = 75,
            release_notifications = ChatConfigDB.ReleaseNotifications.minor,
            media_mode = ChatConfigDB.MediaMode.file,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.domain_model = ChatConfig(
            chat_id = self.chat_id,
            external_id = "chat1",
            language_iso_code = "en",
            language_name = "English",
            title = "Chat One",
            is_private = False,
            reply_chance_percent = 75,
            release_notifications = ChatConfigDB.ReleaseNotifications.minor,
            media_mode = ChatConfigDB.MediaMode.file,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        result = domain(self.db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.db_model.chat_id)
        self.assertEqual(result.external_id, self.db_model.external_id)
        self.assertEqual(result.language_iso_code, self.db_model.language_iso_code)
        self.assertEqual(result.language_name, self.db_model.language_name)
        self.assertEqual(result.title, self.db_model.title)
        self.assertEqual(result.is_private, self.db_model.is_private)
        self.assertEqual(result.reply_chance_percent, self.db_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, self.db_model.release_notifications)
        self.assertEqual(result.media_mode, self.db_model.media_mode)
        self.assertEqual(result.chat_type, self.db_model.chat_type)

    def test_db_maps_all_fields(self):
        result = db(self.domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.external_id, self.domain_model.external_id)
        self.assertEqual(result.language_iso_code, self.domain_model.language_iso_code)
        self.assertEqual(result.language_name, self.domain_model.language_name)
        self.assertEqual(result.title, self.domain_model.title)
        self.assertEqual(result.is_private, self.domain_model.is_private)
        self.assertEqual(result.reply_chance_percent, self.domain_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, self.domain_model.release_notifications)
        self.assertEqual(result.media_mode, self.domain_model.media_mode)
        self.assertEqual(result.chat_type, self.domain_model.chat_type)

    def test_roundtrip_domain_to_db_to_domain(self):
        result = domain(db(self.domain_model))

        self.assertEqual(result, self.domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        domain_model = ChatConfig(
            chat_id = UUID("33333333-3333-3333-3333-333333333333"),
            external_id = "chat2",
            language_iso_code = None,
            language_name = None,
            title = None,
            is_private = True,
            reply_chance_percent = 25,
            release_notifications = ChatConfigDB.ReleaseNotifications.major,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )

        apply_to_db_model(domain_model, self.db_model)

        self.assertEqual(self.db_model.chat_id, self.chat_id)
        self.assertEqual(self.db_model.external_id, domain_model.external_id)
        self.assertIsNone(self.db_model.language_iso_code)
        self.assertIsNone(self.db_model.language_name)
        self.assertIsNone(self.db_model.title)
        self.assertEqual(self.db_model.is_private, domain_model.is_private)
        self.assertEqual(self.db_model.reply_chance_percent, domain_model.reply_chance_percent)
        self.assertEqual(self.db_model.release_notifications, domain_model.release_notifications)
        self.assertEqual(self.db_model.media_mode, domain_model.media_mode)
        self.assertEqual(self.db_model.chat_type, domain_model.chat_type)

    def test_db_leaves_missing_chat_id_for_database_generation(self):
        self.domain_model.chat_id = None

        result = db(self.domain_model)

        self.assertIsNone(result.chat_id)

    def test_from_remote_data_defaults_missing_privacy_to_private(self):
        remote_data = ChatConfigRemoteData(
            external_id = "chat1",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "Chat One",
            language_iso_code = "en",
        )

        result = from_remote_data(remote_data)

        self.assertIsNone(result.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.language_iso_code, remote_data.language_iso_code)
        self.assertEqual(result.title, remote_data.title)
        self.assertTrue(result.is_private)
        self.assertEqual(result.reply_chance_percent, 100)
        self.assertEqual(result.release_notifications, ChatConfigDB.ReleaseNotifications.major)
        self.assertEqual(result.media_mode, ChatConfigDB.MediaMode.photo)
        self.assertEqual(result.chat_type, remote_data.chat_type)

    def test_from_remote_data_sets_public_release_defaults(self):
        remote_data = ChatConfigRemoteData(
            external_id = "chat1",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "Public Chat",
            is_private = False,
        )

        result = from_remote_data(remote_data)

        self.assertFalse(result.is_private)
        self.assertEqual(result.release_notifications, ChatConfigDB.ReleaseNotifications.none)

    def test_apply_remote_data_updates_only_remote_owned_fields(self):
        remote_data = ChatConfigRemoteData(
            external_id = "chat1",
            chat_type = ChatConfigDB.ChatType.telegram,
            title = "Updated Title",
            is_private = True,
            language_iso_code = "fr",
        )

        result = apply_remote_data(self.domain_model, remote_data)

        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.external_id, self.domain_model.external_id)
        self.assertEqual(result.language_iso_code, self.domain_model.language_iso_code)
        self.assertEqual(result.language_name, self.domain_model.language_name)
        self.assertEqual(result.title, "Updated Title")
        self.assertTrue(result.is_private)
        self.assertEqual(result.reply_chance_percent, self.domain_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, self.domain_model.release_notifications)
        self.assertEqual(result.media_mode, self.domain_model.media_mode)
        self.assertEqual(result.chat_type, self.domain_model.chat_type)

    def test_apply_remote_data_ignores_null_remote_values(self):
        remote_data = ChatConfigRemoteData(
            external_id = "chat1",
            chat_type = ChatConfigDB.ChatType.telegram,
            language_iso_code = "fr",
        )

        result = apply_remote_data(self.domain_model, remote_data)

        self.assertEqual(result, self.domain_model)
