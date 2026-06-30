import unittest
from datetime import datetime

from features.chat.whatsapp.model.attachment.media_attachment import MediaAttachment
from features.chat.whatsapp.model.attachment.text import Text
from features.chat.whatsapp.model.change import Change
from features.chat.whatsapp.model.contact import Contact
from features.chat.whatsapp.model.context import Context
from features.chat.whatsapp.model.entry import Entry
from features.chat.whatsapp.model.message import Message
from features.chat.whatsapp.model.metadata import Metadata
from features.chat.whatsapp.model.profile import Profile
from features.chat.whatsapp.model.update import Update
from features.chat.whatsapp.model.value import Value
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from features.users.user_remote_data import UserRemoteData
from util.functions import generate_deterministic_short_uuid


class WhatsAppDomainMapperTest(unittest.TestCase):

    def setUp(self):
        self.mapper = WhatsAppDomainMapper()

    def test_map_update_empty(self):
        update = Update(object = "whatsapp_business_account", entry = [])

        results = self.mapper.map_update(update)
        self.assertEqual(results, [])

    def test_map_update_filled(self):
        # Build typed models end-to-end
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
            text = Text(body = "Hello world"),
        )
        value = Value(
            messaging_product = "whatsapp",
            metadata = Metadata(display_phone_number = "1234567890", phone_number_id = "phone_id"),
            contacts = [Contact(profile = Profile(name = "John Doe"), wa_id = "1234567890")],
            messages = [message],
        )
        change = Change(value = value, field = "messages")
        entry = Entry(id = "1234567890", changes = [change])
        update = Update(object = "whatsapp_business_account", entry = [entry])

        results = self.mapper.map_update(update)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIsNotNone(result.chat)
        self.assertIsNotNone(result.author)
        self.assertIsNotNone(result.message)
        self.assertEqual(result.message.message_id, "100")

    def test_map_update_multiple_entries_picks_latest(self):
        # two entries, two changes/values, ensure latest timestamp is chosen
        now = int(datetime.now().timestamp())

        m1 = Message(id = "m1", **{"from": "1111111111"}, timestamp = str(now - 10), type = "text", text = Text(body = "old msg"))
        v1 = Value(
            messaging_product = "whatsapp",
            metadata = Metadata(display_phone_number = "111", phone_number_id = "phone_id_1"),
            contacts = [Contact(profile = Profile(name = "First User"), wa_id = "1111111111")],
            messages = [m1],
        )
        e1 = Entry(id = "entry_1", changes = [Change(value = v1, field = "messages")])

        m2 = Message(id = "m2", **{"from": "2222222222"}, timestamp = str(now), type = "text", text = Text(body = "new msg"))
        v2 = Value(
            messaging_product = "whatsapp",
            metadata = Metadata(display_phone_number = "222", phone_number_id = "phone_id_2"),
            contacts = [Contact(profile = Profile(name = "Second User"), wa_id = "2222222222")],
            messages = [m2],
        )
        e2 = Entry(id = "entry_2", changes = [Change(value = v2, field = "messages")])

        update = Update(object = "whatsapp_business_account", entry = [e1, e2])

        results = self.mapper.map_update(update)
        # two results (one per message)
        self.assertEqual(len(results), 2)
        # Find the one with latest id
        latest = max(results, key = lambda r: r.message.message_id)
        # author/chat derived from the same value that contained the latest message
        self.assertEqual(latest.message.message_id, "m2")
        self.assertEqual(latest.chat.external_id, "2222222222")
        self.assertEqual(latest.chat.title, "Second User")

    def test_map_update_with_forwarded_message(self):
        message = Message(
            id = "forward_msg_123",
            **{"from": "5511999999999"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            image = MediaAttachment(id = "image_id_123", mime_type = "image/jpeg"),
            context = Context(),
        )

        value = Value(
            messaging_product = "whatsapp",
            metadata = Metadata(display_phone_number = "1234567890", phone_number_id = "phone_id"),
            contacts = [Contact(profile = Profile(name = "John Doe"), wa_id = "5511999999999")],
            messages = [message],
        )
        change = Change(value = value, field = "messages")
        entry = Entry(id = "entry_123", changes = [change])
        update = Update(object = "whatsapp_business_account", entry = [entry])

        results = self.mapper.map_update(update)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.message.message_id, "forward_msg_123")
        self.assertIsNone(result.replied_to_message_id)
        self.assertEqual(len(result.attachments), 1)
        self.assertEqual(result.attachments[0].external_id, "image_id_123")
        self.assertEqual(result.attachments[0].mime_type, "image/jpeg")
        self.assertIn(generate_deterministic_short_uuid("image_id_123"), result.message.text)

    def test_map_message_filled(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
            text = Text(body = "This is a test message"),
        )

        result = self.mapper.map_message(message)

        self.assertEqual(result.message_id, "100")
        self.assertEqual(result.sent_at, datetime.fromtimestamp(int(message.timestamp)))
        self.assertEqual(result.text, "This is a test message")

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

    def test_map_text_filled(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
            text = Text(body = "Hello world"),
        )

        result = self.mapper.map_text(message)

        self.assertEqual(result, "Hello world")

    def test_map_text_empty(self):
        message = Message(
            id = "100",
            **{"from": "1234567890"},
            timestamp = str(int(datetime.now().timestamp())),
            type = "text",
        )

        result = self.mapper.map_text(message)

        self.assertEqual(result, "")

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
