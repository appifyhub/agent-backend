import unittest
from datetime import timedelta
from uuid import uuid4

import stubs

from features.chat.attachment.chat_attachment_mapper import (
    apply_remote_data,
    apply_to_db_model,
    db,
    domain,
    from_remote_data,
)
from util.functions import generate_deterministic_short_uuid


class ChatAttachmentMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_attachment_db()
        domain_model = stubs.domain.chat_attachment()

        result = domain(db_model)

        self.assertEqual(result, domain_model)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_attachment()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(result.external_id, domain_model.external_id)
        self.assertEqual(result.uploader_user_id, domain_model.uploader_user_id)
        self.assertEqual(result.created_at, domain_model.created_at)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.message_id, domain_model.message_id)
        self.assertEqual(result.size, domain_model.size)
        self.assertEqual(result.last_url, domain_model.last_url)
        self.assertEqual(result.extension, domain_model.extension)
        self.assertEqual(result.mime_type, domain_model.mime_type)

    def test_roundtrip_domain_to_db_to_domain(self):
        domain_model = stubs.domain.chat_attachment()

        result = domain(db(domain_model))

        self.assertEqual(result, domain_model)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity_and_creation_metadata(self):
        db_model = stubs.db.chat_attachment_db()
        original_id = db_model.id
        original_uploader_user_id = db_model.uploader_user_id
        original_created_at = db_model.created_at
        domain_model = stubs.domain.chat_attachment(
            id = "different-id",
            external_id = None,
            uploader_user_id = uuid4(),
            created_at = db_model.created_at + timedelta(seconds = 1),
            chat_id = uuid4(),
            message_id = "message2",
            size = None,
            last_url = None,
            extension = "png",
            mime_type = "image/png",
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.id, original_id)
        self.assertIsNone(db_model.external_id)
        self.assertEqual(db_model.uploader_user_id, original_uploader_user_id)
        self.assertEqual(db_model.created_at, original_created_at)
        self.assertEqual(db_model.chat_id, domain_model.chat_id)
        self.assertEqual(db_model.message_id, domain_model.message_id)
        self.assertIsNone(db_model.size)
        self.assertIsNone(db_model.last_url)
        self.assertEqual(db_model.extension, domain_model.extension)
        self.assertEqual(db_model.mime_type, domain_model.mime_type)

    def test_db_maps_random_attachment_id(self):
        domain_model = stubs.domain.chat_attachment(id = uuid4().hex[:8])

        result = db(domain_model)

        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(len(result.id), 8)

    def test_from_remote_data_creates_complete_domain_state(self):
        remote_data = stubs.domain.chat_attachment_remote_data()
        chat_id = stubs.domain.chat_config().chat_id
        uploader_user_id = stubs.domain.user().id

        result = from_remote_data(remote_data, chat_id, uploader_user_id)

        self.assertEqual(result.id, generate_deterministic_short_uuid(remote_data.external_id))
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.uploader_user_id, uploader_user_id)
        self.assertEqual(result.chat_id, chat_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, remote_data.size)
        self.assertEqual(result.last_url, remote_data.last_url)
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_identity_and_applies_truthy_values(self):
        domain_model = stubs.domain.chat_attachment()
        remote_data = stubs.domain.chat_attachment_remote_data(
            external_id = "external2",
            message_id = "message2",
            size = 2048,
            last_url = "https://example.com/file.png",
            extension = "png",
            mime_type = "image/png",
        )

        result = apply_remote_data(domain_model, remote_data)

        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, remote_data.size)
        self.assertEqual(result.last_url, remote_data.last_url)
        self.assertEqual(result.extension, remote_data.extension)
        self.assertEqual(result.mime_type, remote_data.mime_type)

    def test_apply_remote_data_preserves_existing_falsey_remote_metadata(self):
        domain_model = stubs.domain.chat_attachment()
        remote_data = stubs.domain.chat_attachment_remote_data(
            size = 0,
            last_url = "",
            extension = "",
            mime_type = "",
        )

        result = apply_remote_data(domain_model, remote_data)

        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.external_id, remote_data.external_id)
        self.assertEqual(result.message_id, remote_data.message_id)
        self.assertEqual(result.size, domain_model.size)
        self.assertEqual(result.last_url, domain_model.last_url)
        self.assertEqual(result.extension, domain_model.extension)
        self.assertEqual(result.mime_type, domain_model.mime_type)
