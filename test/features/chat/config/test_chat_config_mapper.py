import unittest
from uuid import uuid4

import stubs

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config_mapper import (
    apply_remote_data,
    apply_to_db_model,
    db,
    domain,
    from_remote_data,
)


class ChatConfigMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_config_db()

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, db_model.chat_id)
        self.assertEqual(result.external_id, db_model.external_id)
        self.assertEqual(result.language_iso_code, db_model.language_iso_code)
        self.assertEqual(result.language_name, db_model.language_name)
        self.assertEqual(result.title, db_model.title)
        self.assertEqual(result.is_private, db_model.is_private)
        self.assertEqual(result.reply_chance_percent, db_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, db_model.release_notifications)
        self.assertEqual(result.media_mode, db_model.media_mode)
        self.assertEqual(result.chat_type, db_model.chat_type)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_config()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.external_id, domain_model.external_id)
        self.assertEqual(result.language_iso_code, domain_model.language_iso_code)
        self.assertEqual(result.language_name, domain_model.language_name)
        self.assertEqual(result.title, domain_model.title)
        self.assertEqual(result.is_private, domain_model.is_private)
        self.assertEqual(result.reply_chance_percent, domain_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, domain_model.release_notifications)
        self.assertEqual(result.media_mode, domain_model.media_mode)
        self.assertEqual(result.chat_type, domain_model.chat_type)

    def test_roundtrip_domain_to_db_to_domain(self):
        domain_model = stubs.domain.chat_config()

        result = domain(db(domain_model))

        self.assertEqual(result, domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.chat_config_db()
        original_chat_id = db_model.chat_id
        domain_model = stubs.domain.chat_config(
            chat_id = uuid4(),
            external_id = "chat2",
            language_iso_code = None,
            language_name = None,
            title = None,
            is_private = False,
            reply_chance_percent = 25,
            release_notifications = ChatConfigDB.ReleaseNotifications.minor,
            media_mode = ChatConfigDB.MediaMode.file,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.chat_id, original_chat_id)
        self.assertEqual(db_model.external_id, domain_model.external_id)
        self.assertIsNone(db_model.language_iso_code)
        self.assertIsNone(db_model.language_name)
        self.assertIsNone(db_model.title)
        self.assertEqual(db_model.is_private, domain_model.is_private)
        self.assertEqual(db_model.reply_chance_percent, domain_model.reply_chance_percent)
        self.assertEqual(db_model.release_notifications, domain_model.release_notifications)
        self.assertEqual(db_model.media_mode, domain_model.media_mode)
        self.assertEqual(db_model.chat_type, domain_model.chat_type)

    def test_db_leaves_missing_chat_id_for_database_generation(self):
        domain_model = stubs.domain.chat_config(chat_id = None)

        result = db(domain_model)

        self.assertIsNone(result.chat_id)

    def test_from_remote_data_defaults_missing_privacy_to_private(self):
        remote_data = stubs.domain.chat_config_remote_data()

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
        remote_data = stubs.domain.chat_config_remote_data(is_private = False)

        result = from_remote_data(remote_data)

        self.assertFalse(result.is_private)
        self.assertEqual(result.release_notifications, ChatConfigDB.ReleaseNotifications.none)

    def test_apply_remote_data_updates_only_remote_owned_fields(self):
        domain_model = stubs.domain.chat_config(is_private = False)
        remote_data = stubs.domain.chat_config_remote_data(
            external_id = "chat1",
            title = "Updated Title",
            is_private = True,
            language_iso_code = "fr",
        )

        result = apply_remote_data(domain_model, remote_data)

        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.external_id, domain_model.external_id)
        self.assertEqual(result.language_iso_code, domain_model.language_iso_code)
        self.assertEqual(result.language_name, domain_model.language_name)
        self.assertEqual(result.title, "Updated Title")
        self.assertTrue(result.is_private)
        self.assertEqual(result.reply_chance_percent, domain_model.reply_chance_percent)
        self.assertEqual(result.release_notifications, domain_model.release_notifications)
        self.assertEqual(result.media_mode, domain_model.media_mode)
        self.assertEqual(result.chat_type, domain_model.chat_type)

    def test_apply_remote_data_ignores_null_remote_values(self):
        domain_model = stubs.domain.chat_config()
        remote_data = stubs.domain.chat_config_remote_data()

        result = apply_remote_data(domain_model, remote_data)

        self.assertEqual(result, domain_model)
