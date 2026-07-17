import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.whatsapp.model.response import ContactResponse, MessageResponse, SentMessageResponse
from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK
from features.chat.whatsapp.whatsapp_data_resolver import WhatsAppDataResolver
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper


class WhatsAppBotSDKTest(unittest.TestCase):

    sdk: WhatsAppBotSDK
    mock_di: DI

    def setUp(self):
        # Create mock DI with all required dependencies
        self.mock_di = Mock(spec = DI)

        # noinspection PyPropertyAccess
        self.mock_di.whatsapp_bot_api = Mock(spec = WhatsAppBotAPI)
        # noinspection PyPropertyAccess
        self.mock_di.whatsapp_data_resolver = Mock(spec = WhatsAppDataResolver)
        # noinspection PyPropertyAccess
        self.mock_di.whatsapp_domain_mapper = Mock(spec = WhatsAppDomainMapper)
        # noinspection PyPropertyAccess
        self.mock_di.chat_attachment_repo = Mock()
        self.mock_di.chat_attachment_repo.save.side_effect = lambda attachment: attachment
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = Mock()
        self.mock_di.chat_message_repo.save.side_effect = lambda msg: msg
        self.mock_di.invoker = SimpleNamespace(id = UUID(int = 9))
        self.mock_chat_attachment_service = Mock()
        self.stored_media_url = "s3://the-agent/chats/chat-id/attachments/attachment-id"
        self.public_url = "https://agent.example/attachments/public/token"
        self.mock_chat_attachment_service.is_own_storage_uri.return_value = False
        self.mock_chat_attachment_service.save.side_effect = self.__save_attachment
        self.mock_chat_attachment_service.create_public_url.return_value = SimpleNamespace(url = self.public_url)
        self.mock_di.chat_attachment_service = self.mock_chat_attachment_service

        self.sdk = WhatsAppBotSDK(self.mock_di)

        self.user_id = "001"
        self.chat_id = "123"
        self.message_id = "456"
        self.chat_uuid = UUID("12345678-1234-5678-1234-567812345678")
        self.test_text = "test message"
        self.button_text = "⚙️"
        self.link_url = "https://test.com"

        # Create proper MessageResponse object
        self.api_response = MessageResponse(
            messaging_product = "whatsapp",
            contacts = [ContactResponse(input = "1234567890", wa_id = "1234567890")],
            messages = [SentMessageResponse(id = self.message_id)],
        )

        self.mock_di.whatsapp_bot_api.send_text_message.return_value = self.api_response
        self.mock_di.whatsapp_bot_api.send_image.return_value = self.api_response
        self.mock_di.whatsapp_bot_api.send_document.return_value = self.api_response

        self.chat_config = ChatConfig(
            chat_id = self.chat_uuid,
            external_id = self.chat_id,
            title = "Test Chat",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )

    def __save_attachment(
        self,
        attachment: ChatAttachment,
        content: bytes | None = None,
        remote_url: str | None = None,
    ) -> ChatAttachment:
        if content is None and remote_url is None:
            return attachment
        return replace(attachment, last_url = self.stored_media_url)

    def test_send_text_message(self):
        text = "test message"

        result = self.sdk.send_text_message(chat_config = self.chat_config, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_once_with(
            recipient_id = str(self.chat_id),
            text = text,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.text, text)
        self.assertEqual(result.chat_id, self.chat_uuid)

    def test_send_photo(self):
        caption = "test photo"
        attachment = ChatAttachment(chat_id = self.chat_uuid, uploader_user_id = self.mock_di.invoker.id)

        result = self.sdk.send_photo(
            chat_config = self.chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_image.assert_called_once_with(
            recipient_id = str(self.chat_id),
            image_url = self.public_url,
            caption = caption,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.mock_chat_attachment_service.save.assert_called_once()
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, self.message_id)
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

    def test_send_document(self):
        caption = "test document"
        attachment = ChatAttachment(chat_id = self.chat_uuid, uploader_user_id = self.mock_di.invoker.id)

        result = self.sdk.send_document(
            chat_config = self.chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_document.assert_called_once_with(
            recipient_id = str(self.chat_id),
            document_url = self.public_url,
            caption = caption,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.mock_chat_attachment_service.save.assert_called_once()
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, self.message_id)
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

    def test_set_reaction(self):
        reaction = "👍"
        self.sdk.set_reaction(self.chat_id, self.message_id, reaction)
        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_reaction.assert_called_once_with(
            recipient_id = str(self.chat_id),
            message_id = str(self.message_id),
            emoji = reaction,
        )

    def test_send_button_link(self):
        link_url = "https://test.com"

        # Test settings button
        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
            button_text = "⚙️",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = str(self.chat_id),
            text = f"⚙️ {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

        # Test default-to-settings button
        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = str(self.chat_id),
            text = f"⚙️ {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

        # Test custom button text
        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
            button_text = "test",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_with(
            recipient_id = str(self.chat_id),
            text = f"test {link_url}",
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

    def test_store_api_response_creates_domain_message(self):
        result = self.sdk._WhatsAppBotSDK__store_api_response_as_message(
            self.api_response,
            text = "test",
            chat_id = self.chat_uuid,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)
        self.assertEqual(result.text, "test")
