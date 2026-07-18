import unittest
from datetime import datetime
from uuid import UUID

from db.model.chat_attachment import ChatAttachmentDB
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_mapper import (
    apply_remote_data,
    apply_to_db_model,
    db,
    domain,
    from_remote_data,
)
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from util.functions import generate_deterministic_short_uuid


class ChatAttachmentMapperTest(unittest.TestCase):

    chat_id: UUID
    db_model: ChatAttachmentDB
    domain_model: ChatAttachment

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.uploader_user_id = UUID("22222222-2222-2222-2222-222222222222")
        self.created_at = datetime(2026, 1, 2, 3, 4, 5)
        self.db_model = ChatAttachmentDB(
            id = "attach1",
            external_id = "external1",
            uploader_user_id = self.uploader_user_id,
            created_at = self.created_at,
            chat_id = self.chat_id,
            message_id = "message1",
            size = 1024,
            last_url = "https://example.com/file.jpg",
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        self.domain_model = ChatAttachment(
            id = "attach1",
            external_id = "external1",
            uploader_user_id = self.uploader_user_id,
            created_at = self.created_at,
            chat_id = self.chat_id,
            message_id = "message1",
            size = 1024,
            last_url = "https://example.com/file.jpg",
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
        self.assertEqual(result.uploader_user_id, self.domain_model.uploader_user_id)
        self.assertEqual(result.created_at, self.domain_model.created_at)
        self.assertEqual(result.chat_id, self.domain_model.chat_id)
        self.assertEqual(result.message_id, self.domain_model.message_id)
        self.assertEqual(result.size, self.domain_model.size)
        self.assertEqual(result.last_url, self.domain_model.last_url)
        self.assertEqual(result.extension, self.domain_model.extension)
        self.assertEqual(result.mime_type, self.domain_model.mime_type)

    def test_roundtrip_domain_to_db_to_domain(self):
        result = domain(db(self.domain_model))

        self.assertEqual(result, self.domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity_and_creation_metadata(self):
        domain_model = ChatAttachment(
            id = "different-id",
            external_id = None,
            uploader_user_id = UUID("44444444-4444-4444-4444-444444444444"),
            created_at = datetime(2026, 2, 3, 4, 5, 6),
            chat_id = UUID("33333333-3333-3333-3333-333333333333"),
            message_id = "message2",
            size = None,
            last_url = None,
            extension = "png",
            mime_type = "image/png",
        )

        apply_to_db_model(domain_model, self.db_model)

        self.assertEqual(self.db_model.id, "attach1")
        self.assertIsNone(self.db_model.external_id)
        self.assertEqual(self.db_model.uploader_user_id, self.uploader_user_id)
        self.assertEqual(self.db_model.created_at, self.created_at)
        self.assertEqual(self.db_model.chat_id, domain_model.chat_id)
        self.assertEqual(self.db_model.message_id, domain_model.message_id)
        self.assertIsNone(self.db_model.size)
        self.assertIsNone(self.db_model.last_url)
        self.assertEqual(self.db_model.extension, domain_model.extension)
        self.assertEqual(self.db_model.mime_type, domain_model.mime_type)

    def test_new_domain_model_generates_id_before_db_mapping(self):
        domain_model = ChatAttachment(
            external_id = "external3",
            chat_id = self.chat_id,
            uploader_user_id = self.uploader_user_id,
            message_id = "message3",
        )

        result = db(domain_model)

        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(len(result.id), 8)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = ChatAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 2048,
            last_url = "https://example.com/file.png",
            extension = "png",
            mime_type = "image/png",
        )

        result = from_remote_data(remote_data, self.chat_id, self.uploader_user_id)

        self.assertEqual(result.id, generate_deterministic_short_uuid(remote_data.external_id))
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.uploader_user_id, self.uploader_user_id)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, remote_data.size)
        self.assertEqual(result.last_url, remote_data.last_url)
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_identity_and_applies_truthy_values(self):
        remote_data = ChatAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 2048,
            last_url = "https://example.com/file.png",
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
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_existing_falsey_remote_metadata(self):
        remote_data = ChatAttachmentRemoteData(
            external_id = "external2",
            message_id = "message2",
            size = 0,
            last_url = "",
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
        self.assertEqual(result.extension, self.domain_model.extension)
        self.assertEqual(result.mime_type, self.domain_model.mime_type)
