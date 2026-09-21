import unittest
from unittest.mock import Mock

import stubs

from di.di import DI
from features.chat.message.chat_message import ChatMessage
from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK


class WhatsAppBotSDKTest(unittest.TestCase):

    sdk: WhatsAppBotSDK
    mock_di: DI

    def setUp(self):
        # Create mock DI with all required dependencies
        self.mock_di = Mock(spec = DI)

        # noinspection PyPropertyAccess
        self.mock_di.whatsapp_bot_api = Mock(spec = WhatsAppBotAPI)
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = Mock()
        self.mock_di.chat_message_repo.save.side_effect = lambda msg: msg
        self.mock_chat_attachment_service = Mock()
        self.mock_chat_attachment_service.create_public_url.return_value = stubs.domain.public_attachment()
        self.mock_di.chat_attachment_service = self.mock_chat_attachment_service

        self.sdk = WhatsAppBotSDK(self.mock_di)

    def test_send_text_message(self):
        text = "test message"
        chat_config = stubs.domain.chat_config()
        api_response = stubs.external.whatsapp_message_response()
        self.mock_di.whatsapp_bot_api.send_text_message.return_value = api_response

        result = self.sdk.send_text_message(chat_config = chat_config, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_once_with(
            recipient_id = chat_config.external_id,
            text = text,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.text, text)
        self.assertEqual(result.chat_id, chat_config.chat_id)

    def test_send_photo(self):
        caption = "test photo"
        chat_config = stubs.domain.chat_config()
        api_response = stubs.external.whatsapp_message_response()
        self.mock_di.whatsapp_bot_api.send_image.return_value = api_response
        attachment = stubs.domain.chat_attachment(
            id = "local123",
            mime_type = None,
        )
        public_url = self.mock_chat_attachment_service.create_public_url.return_value.url

        result = self.sdk.send_photo(
            chat_config = chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_image.assert_called_once_with(
            recipient_id = chat_config.external_id,
            image_url = public_url,
            caption = caption,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.mock_chat_attachment_service.save.assert_called_once()
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.text, "test photo\n\n📎 [ local123 ]")
        self.assertEqual(result.chat_id, chat_config.chat_id)

    def test_send_document(self):
        caption = "test document"
        chat_config = stubs.domain.chat_config()
        api_response = stubs.external.whatsapp_message_response()
        self.mock_di.whatsapp_bot_api.send_document.return_value = api_response
        attachment = stubs.domain.chat_attachment(
            id = "local456",
            extension = "pdf",
            mime_type = None,
        )
        public_url = self.mock_chat_attachment_service.create_public_url.return_value.url

        result = self.sdk.send_document(
            chat_config = chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_document.assert_called_once_with(
            recipient_id = chat_config.external_id,
            document_url = public_url,
            caption = caption,
            filename = "local456.pdf",
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.mock_chat_attachment_service.save.assert_called_once()
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.text, "test document\n\n📎 [ local456 ]")
        self.assertEqual(result.chat_id, chat_config.chat_id)

    def test_send_video(self):
        caption = "test video"
        chat_config = stubs.domain.chat_config()
        api_response = stubs.external.whatsapp_message_response()
        self.mock_di.whatsapp_bot_api.send_video.return_value = api_response
        attachment = stubs.domain.chat_attachment(
            id = "local789",
            mime_type = "video/mp4",
        )
        public_url = self.mock_chat_attachment_service.create_public_url.return_value.url

        result = self.sdk.send_video(
            chat_config = chat_config,
            attachment = attachment,
            caption = caption,
        )

        self.mock_di.whatsapp_bot_api.send_video.assert_called_once_with(
            recipient_id = chat_config.external_id,
            video_url = public_url,
            caption = caption,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.text, "test video\n\n📎 [ local789 (video/mp4) ]")
        self.assertEqual(result.chat_id, chat_config.chat_id)

    def test_set_reaction(self):
        chat_id = stubs.domain.chat_config().external_id
        message_id = stubs.external.whatsapp_sent_message_response().id
        reaction = "👍"

        self.sdk.set_reaction(chat_id, message_id, reaction)
        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_reaction.assert_called_once_with(
            recipient_id = chat_id,
            message_id = message_id,
            emoji = reaction,
        )

    def test_send_button_link(self):
        link_url = "https://test.example.com/settings/key123"
        chat_config = stubs.domain.chat_config()
        api_response = stubs.external.whatsapp_message_response()
        self.mock_di.whatsapp_bot_api.send_text_message.return_value = api_response

        # Test settings button
        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
            button_text = "⚙️",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = chat_config.external_id,
            text = f"⚙️ {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.chat_id, chat_config.chat_id)
        self.assertEqual(result.text, "⚙️ test...123")

        # Test default-to-settings button
        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = chat_config.external_id,
            text = f"⚙️ {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.chat_id, chat_config.chat_id)
        self.assertEqual(result.text, "⚙️ test...123")

        # Test custom button text
        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
            button_text = "test",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = chat_config.external_id,
            text = f"test {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.chat_id, chat_config.chat_id)
        self.assertEqual(result.text, "test test...123")

    def test_store_api_response_creates_domain_message(self):
        api_response = stubs.external.whatsapp_message_response()
        chat_id = stubs.domain.chat_config().chat_id

        result = self.sdk._WhatsAppBotSDK__store_api_response_as_message(
            api_response,
            text = "test",
            chat_id = chat_id,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, api_response.messages[0].id)
        self.assertEqual(result.chat_id, chat_id)
        self.assertEqual(result.text, "test")
