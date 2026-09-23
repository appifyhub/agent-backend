import unittest
from datetime import datetime, timedelta
from uuid import uuid4

import stubs

from features.chat.message.chat_message_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data


class ChatMessageMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_chat_message_accepts_current_sent_at(self):
        before = datetime.now()

        result = stubs.domain.chat_message(sent_at = datetime.now())

        after = datetime.now()
        self.assertGreaterEqual(result.sent_at, before)
        self.assertLessEqual(result.sent_at, after)

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_message_db()
        domain_model = stubs.domain.chat_message()

        result = domain(db_model)

        self.assertEqual(result, domain_model)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_message()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.message_id, domain_model.message_id)
        self.assertEqual(result.ingestion_order, domain_model.ingestion_order)
        self.assertEqual(result.author_id, domain_model.author_id)
        self.assertEqual(result.sent_at, domain_model.sent_at)
        self.assertEqual(result.text, domain_model.text)
        self.assertEqual(result.is_temporary, domain_model.is_temporary)

    def test_roundtrip_domain_to_db_to_domain(self):
        domain_model = stubs.domain.chat_message()

        result = domain(db(domain_model))

        self.assertEqual(result, domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.chat_message_db()
        original_chat_id = db_model.chat_id
        original_message_id = db_model.message_id
        original_ingestion_order = db_model.ingestion_order
        domain_model = stubs.domain.chat_message(
            chat_id = uuid4(),
            message_id = "message2",
            ingestion_order = db_model.ingestion_order + 1,
            author_id = None,
            sent_at = db_model.sent_at + timedelta(minutes = 1),
            text = "Replacement",
            is_temporary = True,
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.chat_id, original_chat_id)
        self.assertEqual(db_model.message_id, original_message_id)
        self.assertEqual(db_model.ingestion_order, original_ingestion_order)
        self.assertIsNone(db_model.author_id)
        self.assertEqual(db_model.sent_at, domain_model.sent_at)
        self.assertEqual(db_model.text, domain_model.text)
        self.assertEqual(db_model.is_temporary, domain_model.is_temporary)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = stubs.domain.chat_message_remote_data()
        chat_id = stubs.domain.chat_config().chat_id
        author_id = stubs.domain.user().id

        result = from_remote_data(remote_data, chat_id, author_id)

        self.assertEqual(result.chat_id, chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertIsNone(result.ingestion_order)
        self.assertEqual(result.author_id, author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
        self.assertFalse(result.is_temporary)

    def test_apply_remote_data_preserves_identity_and_applies_resolved_author(self):
        domain_model = stubs.domain.chat_message()
        new_author_id = uuid4()
        remote_data = stubs.domain.chat_message_remote_data(
            message_id = "different-message",
            sent_at = domain_model.sent_at + timedelta(minutes = 1),
            text = "Edited message",
        )

        result = apply_remote_data(domain_model, remote_data, new_author_id)

        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.message_id, domain_model.message_id)
        self.assertEqual(result.ingestion_order, domain_model.ingestion_order)
        self.assertEqual(result.author_id, new_author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
        self.assertEqual(result.is_temporary, domain_model.is_temporary)

    def test_apply_remote_data_preserves_existing_author_when_unresolved(self):
        domain_model = stubs.domain.chat_message()
        remote_data = stubs.domain.chat_message_remote_data(
            sent_at = domain_model.sent_at + timedelta(minutes = 1),
            text = "Edited message",
        )

        result = apply_remote_data(domain_model, remote_data, None)

        self.assertEqual(result.author_id, domain_model.author_id)
        self.assertEqual(result.ingestion_order, domain_model.ingestion_order)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
