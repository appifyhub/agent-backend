import unittest
from uuid import UUID

from db.model.chat_message_attachment import ChatMessageAttachmentDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_mapper import (
    apply_remote_data,
    db,
    domain,
    from_remote_data,
)
from features.chat.attachment.chat_message_attachment_remote_data import ChatMessageAttachmentRemoteData


class ChatMessageAttachmentMapperTest(unittest.TestCase):

    chat_id: UUID
    db_model: ChatMessageAttachmentDB
    domain_model: ChatMessageAttachment

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.db_model = ChatMessageAttachmentDB(
            id = "attach1",
            external_id = "external1",
            chat_id = self.chat_id,
            message_id = "message1",
            size = 1024,
            last_url = "https://example.com/file.jpg",
            last_url_until = 1234567890,
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        self.domain_model = ChatMessageAttachment(
            id = "attach1",
            external_id = "external1",
            chat_id = self.chat_id,
            message_id = "message1",
            size = 1024,
            last_url = "https://example.com/file.jpg",
            last_url_until = 1234567890,
            extension = "jpg",
            mime_type = "image/jpeg",
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
        self.assertEqual(result.id, self.domain_model.id)
        self.assertEqual(result.external_id, self.domain_model.external_id)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.message_id, self.domain_model.message_id)
        self.assertEqual(result.size, self.domain_model.size)
        self.assertEqual(result.last_url, self.domain_model.last_url)
        self.assertEqual(result.last_url_until, self.domain_model.last_url_until)
        self.assertEqual(result.extension, self.domain_model.extension)
        self.assertEqual(result.mime_type, self.domain_model.mime_type)

    def test_roundtrip_domain_to_db_to_domain(self):
        result = domain(db(self.domain_model))

        self.assertEqual(result, self.domain_model)

    def test_db_leaves_missing_id_for_database_generation(self):
        self.domain_model.id = None

        result = db(self.domain_model)

        self.assertIsNone(result.id)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = ChatMessageAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 2048,
            last_url = "https://example.com/file.png",
            last_url_until = 9876543210,
            extension = "png",
            mime_type = "image/png",
        )

        result = from_remote_data(remote_data, self.chat_id)

        self.assertEqual(result.id, "778202be")
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, remote_data.size)
        self.assertEqual(result.last_url, remote_data.last_url)
        self.assertEqual(result.last_url_until, remote_data.last_url_until)
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_identity_and_applies_truthy_values(self):
        remote_data = ChatMessageAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 2048,
            last_url = "https://example.com/file.png",
            last_url_until = 9876543210,
            extension = "png",
            mime_type = "image/png",
        )

        result = apply_remote_data(self.domain_model, remote_data)

        self.assertEqual(result.id, self.domain_model.id)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, remote_data.size)
        self.assertEqual(result.last_url, remote_data.last_url)
        self.assertEqual(result.last_url_until, remote_data.last_url_until)
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_existing_falsey_remote_metadata(self):
        remote_data = ChatMessageAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 0,
            last_url = "",
            last_url_until = 0,
            extension = "",
            mime_type = "",
        )

        result = apply_remote_data(self.domain_model, remote_data)

        self.assertEqual(result.id, self.domain_model.id)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, self.domain_model.size)
        self.assertEqual(result.last_url, self.domain_model.last_url)
        self.assertEqual(result.last_url_until, self.domain_model.last_url_until)
        self.assertEqual(result.extension, self.domain_model.extension)
        self.assertEqual(result.mime_type, self.domain_model.mime_type)
