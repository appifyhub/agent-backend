import unittest
from datetime import datetime, timedelta
from uuid import UUID

from db.model.chat_message import ChatMessageDB
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData


class ChatMessageMapperTest(unittest.TestCase):

    chat_id: UUID
    author_id: UUID
    sent_at: datetime
    db_model: ChatMessageDB
    domain_model: ChatMessage

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.author_id = UUID("22222222-2222-2222-2222-222222222222")
        self.sent_at = datetime(2026, 1, 2, 12, 0, 0)
        self.db_model = ChatMessageDB(
            chat_id = self.chat_id,
            message_id = "message1",
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
        )
        self.domain_model = ChatMessage(
            chat_id = self.chat_id,
            message_id = "message1",
            author_id = self.author_id,
            sent_at = self.sent_at,
            text = "Hello",
        )

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        result = domain(self.db_model)

        self.assertEqual(result, self.domain_model)

    def test_db_maps_all_fields(self):
        result = db(self.domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.message_id, self.domain_model.message_id)
        self.assertEqual(result.author_id, self.domain_model.author_id)
        self.assertEqual(result.sent_at, self.domain_model.sent_at)
        self.assertEqual(result.text, self.domain_model.text)

    def test_roundtrip_domain_to_db_to_domain(self):
        result = domain(db(self.domain_model))

        self.assertEqual(result, self.domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        domain_model = ChatMessage(
            chat_id = UUID("33333333-3333-3333-3333-333333333333"),
            message_id = "message2",
            author_id = None,
            sent_at = self.sent_at + timedelta(minutes = 1),
            text = "Replacement",
        )

        apply_to_db_model(domain_model, self.db_model)

        self.assertEqual(self.db_model.chat_id, self.chat_id)
        self.assertEqual(self.db_model.message_id, "message1")
        self.assertIsNone(self.db_model.author_id)
        self.assertEqual(self.db_model.sent_at, domain_model.sent_at)
        self.assertEqual(self.db_model.text, domain_model.text)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = ChatMessageRemoteData(
            message_id = "message2",
            sent_at = self.sent_at,
            text = "Remote message",
        )

        result = from_remote_data(remote_data, self.chat_id, self.author_id)

        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.author_id, self.author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)

    def test_apply_remote_data_preserves_identity_and_applies_resolved_author(self):
        new_author_id = UUID("33333333-3333-3333-3333-333333333333")
        remote_data = ChatMessageRemoteData(
            message_id = "different-message",
            sent_at = self.sent_at + timedelta(minutes = 1),
            text = "Edited message",
        )

        result = apply_remote_data(self.domain_model, remote_data, new_author_id)

        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.message_id, self.domain_model.message_id)
        self.assertEqual(result.author_id, new_author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)

    def test_apply_remote_data_preserves_existing_author_when_unresolved(self):
        remote_data = ChatMessageRemoteData(
            message_id = self.domain_model.message_id,
            sent_at = self.sent_at + timedelta(minutes = 1),
            text = "Edited message",
        )

        result = apply_remote_data(self.domain_model, remote_data, None)

        self.assertEqual(result.author_id, self.domain_model.author_id)
        self.assertEqual(result.sent_at, remote_data.sent_at)
        self.assertEqual(result.text, remote_data.text)
