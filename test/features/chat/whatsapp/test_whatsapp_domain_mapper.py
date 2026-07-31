import unittest
from datetime import datetime

from features.chat.whatsapp.model.attachment.media_attachment import MediaAttachment
from features.chat.whatsapp.model.attachment.text import Text
from features.chat.whatsapp.model.context import Context
from features.chat.whatsapp.model.message import Message
from features.chat.whatsapp.model.value import Value
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from features.users.user_remote_data import UserRemoteData


class WhatsAppDomainMapperTest(unittest.TestCase):

    def setUp(self):
        self.mapper = WhatsAppDomainMapper()

    def test_map_message_filled(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
            text = Text(body = "This is a test message"),
            context = Context(id = "old-message"),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.sent_at, datetime.fromtimestamp(int(message.timestamp)))
        self.assertEqual(result.text, "This is a test message")
        self.assertEqual(result.replied_to_message_id, "old-message")
        self.assertIsNone(result.quote_text)

    def test_map_message_empty(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.sent_at, datetime.fromtimestamp(int(message.timestamp)))
        self.assertEqual(result.text, "")
        self.assertIsNone(result.replied_to_message_id)
        self.assertIsNone(result.quote_text)

    def test_map_message_uses_media_caption(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            image = MediaAttachment(
                id = "image_id",
                mime_type = "image/jpeg",
                caption = "This is a caption",
            ),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.text, "This is a caption")

    def test_map_message_uses_video_caption(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "video",
            video = MediaAttachment(
                id = "video_id",
                mime_type = "video/mp4",
                caption = "This is a video caption",
            ),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.text, "This is a video caption")

    def test_map_author_filled(self):
        value_dict = {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "1234567890",
                "phone_number_id": "phone_id",
            },
            "contacts": [{
                "profile": {"name": "John Doe"},
                "wa_id": "1234567890",
            }],
            "messages": [],
        }

        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        value_obj = Value.model_validate(value_dict)
        result = self.mapper.map_author(message, value_obj)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, UserRemoteData)
        self.assertEqual(result.full_name, "John Doe")
        self.assertEqual(result.whatsapp_user_id, "1234567890")
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "1234567890")

    def test_map_author_empty(self):
        value_dict = {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "1234567890",
                "phone_number_id": "phone_id",
            },
            "contacts": [],
            "messages": [],
        }
        value = Value.model_validate(value_dict)

        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_author(message, value)

        self.assertIsNotNone(result)
        self.assertEqual(result.whatsapp_user_id, "1234567890")

    def test_map_author_uses_contact_matching_message_sender(self):
        value = Value.model_validate({
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "1234567890",
                "phone_number_id": "phone_id",
            },
            "contacts": [
                {"profile": {"name": "Unrelated"}, "wa_id": "999"},
                {"profile": {"name": "John Doe"}, "wa_id": "1234567890"},
            ],
            "messages": [],
        })
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_author(message, value)

        assert result is not None
        self.assertEqual(result.full_name, "John Doe")
        self.assertEqual(result.whatsapp_user_id, "1234567890")

    def test_map_chat_filled(self):
        value_dict = {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "1234567890",
                "phone_number_id": "phone_id",
            },
            "contacts": [{
                "profile": {"name": "John Doe"},
                "wa_id": "1234567890",
            }],
            "messages": [],
        }

        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        value_obj = Value.model_validate(value_dict)
        result = self.mapper.map_chat(message, value_obj)

        self.assertIsNotNone(result)
        self.assertEqual(result.external_id, "1234567890")
        self.assertEqual(result.title, "John Doe")
        self.assertTrue(result.is_private)
        self.assertEqual(result.chat_type.value, "whatsapp")

    def test_map_chat_uses_contact_matching_message_sender(self):
        value = Value.model_validate({
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "1234567890",
                "phone_number_id": "phone_id",
            },
            "contacts": [
                {"profile": {"name": "Unrelated"}, "wa_id": "999"},
                {"profile": {"name": "John Doe"}, "wa_id": "1234567890"},
            ],
            "messages": [],
        })
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_chat(message, value)

        self.assertEqual(result.external_id, "1234567890")
        self.assertEqual(result.title, "John Doe")

    def test_map_attachments_filled(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            image = MediaAttachment(
                id = "image_id",
                mime_type = "image/jpeg",
            ),
        )

        result = self.mapper.map_attachments(message)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].external_id, "image_id")
        self.assertEqual(result[0].mime_type, "image/jpeg")

    def test_map_attachments_empty(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_attachments(message)

        self.assertEqual(len(result), 0)

    def test_map_attachments_video(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "video",
            video = MediaAttachment(
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
