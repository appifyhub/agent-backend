import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import stubs

from features.chat.message.chat_message_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data


class ChatMessageMapperTest(unittest.TestCase):

    chat_id: UUID
    author_id: UUID
    sent_at: datetime

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.author_id = UUID("22222222-2222-2222-2222-222222222222")
        self.sent_at = datetime(2026, 1, 2, 12, 0, 0)

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_message_db(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )

        result = domain(db_model)

        self.assertEqual(result, domain_model)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )

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
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )

        result = domain(db(domain_model))

        self.assertEqual(result, domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.chat_message_db(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )

        domain_model = replace(
            domain_model,
            chat_id = UUID("33333333-3333-3333-3333-333333333333"),
            message_id = "message2",
            author_id = None,
            sent_at = self.sent_at + timedelta(minutes = 1),
            text = "Replacement",
            is_temporary = False,
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.chat_id, self.chat_id)
        self.assertEqual(db_model.message_id, "message1")
        self.assertEqual(db_model.ingestion_order, domain_model.ingestion_order)
        self.assertIsNone(db_model.author_id)
        self.assertEqual(db_model.sent_at, domain_model.sent_at)
        self.assertEqual(db_model.text, domain_model.text)
        self.assertEqual(db_model.is_temporary, domain_model.is_temporary)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = stubs.domain.chat_message_remote_data(
            message_id = "message2",
            sent_at = self.sent_at,
            text = "Remote message",
        )

        result = from_remote_data(remote_data, self.chat_id, self.author_id)

        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertIsNone(result.ingestion_order)
        self.assertEqual(result.author_id, self.author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
        self.assertFalse(result.is_temporary)

    def test_apply_remote_data_preserves_identity_and_applies_resolved_author(self):
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )
        new_author_id = UUID("33333333-3333-3333-3333-333333333333")
        remote_data = stubs.domain.chat_message_remote_data(
            message_id = "different-message",
            sent_at = self.sent_at + timedelta(minutes = 1),
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
        domain_model = stubs.domain.chat_message(
            chat_id = self.chat_id,
            message_id = "message1",
            ingestion_order = 7,
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
            is_temporary = True,
        )
        remote_data = stubs.domain.chat_message_remote_data(
            message_id = domain_model.message_id,
            sent_at = self.sent_at + timedelta(minutes = 1),
            text = "Edited message",
        )

        result = apply_remote_data(domain_model, remote_data, None)

        self.assertEqual(result.author_id, domain_model.author_id)
        self.assertEqual(result.ingestion_order, domain_model.ingestion_order)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
