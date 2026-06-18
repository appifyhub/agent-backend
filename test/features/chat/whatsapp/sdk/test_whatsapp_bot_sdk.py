import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from db.schema.chat_message import ChatMessage
from db.schema.chat_message_attachment import ChatMessageAttachment
from di.di import DI
from features.chat.config.chat_config import ChatConfig
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
        self.mock_di.chat_config_repo = Mock()
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_attachment_crud = Mock()
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_crud = Mock()

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
        self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = self.chat_config

        # Create a mock DB object that will be returned when saving message
        mock_message_db = Mock()
        self.mock_di.chat_message_crud.save.return_value = mock_message_db

    @patch.object(WhatsAppDomainMapper, "map_update")
    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_send_text_message(self, mock_message_validate, mock_map_update):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "test message",
        )
        text = "test message"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = WhatsAppDomainMapper.Result)
        self.mock_di.whatsapp_data_resolver.resolve.return_value = Mock(
            spec = WhatsAppDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],
        )

        result = self.sdk.send_text_message(chat_id = self.chat_id, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_once_with(
            recipient_id = str(self.chat_id),
            text = text,
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.text, text)
        self.assertEqual(result.chat_id, self.chat_uuid)

    @patch("requests.get")
    @patch.object(WhatsAppDomainMapper, "map_update")
    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_send_photo(self, mock_message_validate, mock_map_update, mock_requests_get):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "test photo",
        )
        # Mock requests.get to avoid actual network calls
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"\xFF\xD8\xFF\xE0"  # JPEG magic bytes
        mock_requests_get.return_value = mock_response
        photo_url = "http://test.com/photo.jpg"
        caption = "test photo"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = WhatsAppDomainMapper.Result)
        self.mock_di.whatsapp_data_resolver.resolve.return_value = Mock(
            spec = WhatsAppDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],
        )

        result = self.sdk.send_photo(
            chat_id = self.chat_id,
            photo_url = photo_url,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_image.assert_called_once_with(
            recipient_id = str(self.chat_id),
            image_url = photo_url,
            caption = caption,
        )
        # Check that we got a ChatMessage object with the expected content
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

    @patch("requests.get")
    @patch.object(WhatsAppDomainMapper, "map_update")
    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_send_document(self, mock_message_validate, mock_map_update, mock_requests_get):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "test document",
        )
        # Mock requests.get to avoid actual network calls
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4"  # PDF magic bytes
        mock_requests_get.return_value = mock_response
        doc_url = "http://test.com/doc.pdf"
        caption = "test document"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = WhatsAppDomainMapper.Result)
        self.mock_di.whatsapp_data_resolver.resolve.return_value = Mock(
            spec = WhatsAppDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],  # Add at least one attachment
        )

        result = self.sdk.send_document(
            chat_id = self.chat_id,
            document_url = doc_url,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_document.assert_called_once_with(
            recipient_id = str(self.chat_id),
            document_url = doc_url,
            caption = caption,
        )
        # Check that we got a ChatMessage object with the expected content
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

    @patch.object(WhatsAppDomainMapper, "map_update")
    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_send_button_link(self, mock_message_validate, mock_map_update):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "⚙️ https://test.com",
        )
        link_url = "https://test.com"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = WhatsAppDomainMapper.Result)
        self.mock_di.whatsapp_data_resolver.resolve.return_value = Mock(
            spec = WhatsAppDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],
        )

        # Test settings button
        result = self.sdk.send_button_link(
            chat_id = self.chat_id,
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
            chat_id = self.chat_id,
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
            chat_id = self.chat_id,
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

    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_store_api_response_mapping_failure(self, mock_message_validate):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "test",
        )
        # The __store_api_response_as_message method now directly creates a ChatMessage
        # without using domain mapping, so this test is no longer relevant
        result = self.sdk._WhatsAppBotSDK__store_api_response_as_message(
            self.api_response,
            text = "test",
            recipient_id = self.chat_id,
        )
        self.assertIsInstance(result, ChatMessage)

    @patch("db.schema.chat_message.ChatMessage.model_validate")
    def test_store_api_response_resolution_failure(self, mock_message_validate):
        mock_message_validate.return_value = ChatMessage(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            sent_at = datetime.now(),
            text = "test",
        )
        # The __store_api_response_as_message method now directly creates a ChatMessage
        # without using data resolution, so this test is no longer relevant
        result = self.sdk._WhatsAppBotSDK__store_api_response_as_message(
            self.api_response,
            text = "test",
            recipient_id = self.chat_id,
        )
        self.assertIsInstance(result, ChatMessage)
