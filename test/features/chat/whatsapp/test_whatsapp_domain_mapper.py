import unittest
from datetime import datetime

import stubs

from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from features.users.user_remote_data import UserRemoteData


class WhatsAppDomainMapperTest(unittest.TestCase):

    def setUp(self):
        self.mapper = WhatsAppDomainMapper()

    def test_map_message_filled(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = stubs.external.whatsapp_text(body = "This is a test message"),
            context = stubs.external.whatsapp_context(id = "old-message"),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.sent_at, datetime.fromtimestamp(int(message.timestamp)))
        self.assertEqual(result.text, "This is a test message")
        self.assertEqual(result.replied_to_message_id, "old-message")
        self.assertIsNone(result.quote_text)

    def test_map_message_empty(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.sent_at, datetime.fromtimestamp(int(message.timestamp)))
        self.assertEqual(result.text, "")
        self.assertIsNone(result.replied_to_message_id)
        self.assertIsNone(result.quote_text)

    def test_map_message_uses_media_caption(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            text = None,
            image = stubs.external.whatsapp_media_attachment(
                id = "image_id",
                mime_type = "image/jpeg",
                caption = "This is a caption",
            ),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.text, "This is a caption")

    def test_map_message_uses_video_caption(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            type = "video",
            text = None,
            video = stubs.external.whatsapp_media_attachment(
                id = "video_id",
                mime_type = "video/mp4",
                caption = "This is a video caption",
            ),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.text, "This is a video caption")

    def test_map_author_filled(self):
        value_obj = stubs.external.whatsapp_value(
            metadata = stubs.external.whatsapp_metadata(
                display_phone_number = "1234567890",
                phone_number_id = "phone_id",
            ),
            contacts = [
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "John Doe"),
                    wa_id = "1234567890",
                ),
            ],
        )
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
            **{"from": "1234567890"},
        )

        result = self.mapper.map_author(message, value_obj)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserRemoteData)
        self.assertEqual(result.full_name, "John Doe")
        self.assertEqual(result.whatsapp_user_id, "1234567890")
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "1234567890")

    def test_map_author_empty(self):
        value = stubs.external.whatsapp_value(contacts = [])
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
            **{"from": "1234567890"},
        )

        result = self.mapper.map_author(message, value)

        self.assertIsNotNone(result)
        self.assertEqual(result.whatsapp_user_id, "1234567890")

    def test_map_author_uses_contact_matching_message_sender(self):
        value = stubs.external.whatsapp_value(
            contacts = [
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "Unrelated"),
                    wa_id = "999",
                ),
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "John Doe"),
                    wa_id = "1234567890",
                ),
            ],
        )
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
            **{"from": "1234567890"},
        )

        result = self.mapper.map_author(message, value)

        assert result is not None
        self.assertEqual(result.full_name, "John Doe")
        self.assertEqual(result.whatsapp_user_id, "1234567890")

    def test_map_chat_filled(self):
        value_obj = stubs.external.whatsapp_value(
            contacts = [
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "John Doe"),
                    wa_id = "1234567890",
                ),
            ],
        )
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
            **{"from": "1234567890"},
        )

        result = self.mapper.map_chat(message, value_obj)

        self.assertIsNotNone(result)
        self.assertEqual(result.external_id, "1234567890")
        self.assertEqual(result.title, "John Doe")
        self.assertTrue(result.is_private)
        self.assertEqual(result.chat_type.value, "whatsapp")

    def test_map_chat_uses_contact_matching_message_sender(self):
        value = stubs.external.whatsapp_value(
            contacts = [
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "Unrelated"),
                    wa_id = "999",
                ),
                stubs.external.whatsapp_contact(
                    profile = stubs.external.whatsapp_profile(name = "John Doe"),
                    wa_id = "1234567890",
                ),
            ],
        )
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
            **{"from": "1234567890"},
        )

        result = self.mapper.map_chat(message, value)

        self.assertEqual(result.external_id, "1234567890")
        self.assertEqual(result.title, "John Doe")

    def test_map_attachments_filled(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            text = None,
            image = stubs.external.whatsapp_media_attachment(
                id = "image_id",
                mime_type = "image/jpeg",
            ),
        )

        result = self.mapper.map_attachments(message)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].external_id, "image_id")
        self.assertEqual(result[0].mime_type, "image/jpeg")

    def test_map_attachments_empty(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            text = None,
        )

        result = self.mapper.map_attachments(message)

        self.assertEqual(len(result), 0)

    def test_map_attachments_video(self):
        message = stubs.external.whatsapp_message(
            id = "100",
            timestamp = str(int(datetime.now().timestamp())),
            type = "video",
            text = None,
            video = stubs.external.whatsapp_media_attachment(
                id = "video_id",
                mime_type = "video/mp4",
            ),
        )

        result = self.mapper.map_attachments(message)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].external_id, "video_id")
        self.assertEqual(result[0].message_id, "100")
        self.assertEqual(result[0].mime_type, "video/mp4")

    def test_map_to_attachment_filled(self):
        media_id = "123"
        message_id = "100"
        mime_type = "image/jpeg"

        result = self.mapper.map_to_attachment(media_id = media_id, message_id = message_id, mime_type = mime_type)

        self.assertEqual(result.external_id, "123")
        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.mime_type, "image/jpeg")

    def test_map_to_attachment_empty(self):
        media_id = "123"
        message_id = "100"

        result = self.mapper.map_to_attachment(media_id = media_id, message_id = message_id, mime_type = None)

        self.assertEqual(result.external_id, "123")
        self.assertEqual(result.message_id, "100")
        self.assertIsNone(result.mime_type)

    def test_resolve_chat_name_filled(self):
        result = self.mapper.resolve_chat_name(
            chat_id = "10",
            contact_name = "John Doe",
        )

        self.assertEqual(result, "John Doe")

    def test_resolve_chat_name_partial(self):
        result = self.mapper.resolve_chat_name(
            chat_id = "10",
            contact_name = "John",
        )

        self.assertEqual(result, "John")

    def test_resolve_chat_name_empty(self):
        result = self.mapper.resolve_chat_name(
            chat_id = "10",
            contact_name = None,
        )

        self.assertEqual(result, "#10")
