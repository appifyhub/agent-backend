import unittest
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.supported_files import resolve_file_type
from features.chat.whatsapp.model.media_info import MediaInfo
from features.chat.whatsapp.model.response import ContactResponse, MessageResponse, SentMessageResponse
from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK
from features.chat.whatsapp.whatsapp_data_resolver import WhatsAppDataResolver
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from util.error_codes import ATTACHMENT_STORAGE_FAILED
from util.errors import ExternalServiceError, InternalError, NotFoundError


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
        self.mock_di.chat_message_attachment_repo = Mock()
        self.mock_di.chat_message_attachment_repo.save.side_effect = lambda attachment: attachment
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = Mock()
        self.mock_di.chat_message_repo.save.side_effect = lambda msg: msg
        self.mock_di.invoker = SimpleNamespace(id = UUID(int = 9))
        self.mock_chat_message_attachment_service = Mock()
        self.stored_media_url = "s3://the-agent/chats/chat-id/attachments/attachment-id"
        self.mock_chat_message_attachment_service.is_own_storage_uri.return_value = False
        self.mock_chat_message_attachment_service.save.side_effect = self.__save_attachment
        self.mock_di.chat_message_attachment_service = self.mock_chat_message_attachment_service

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

        self.attachment = ChatMessageAttachment(
            id = "attachment1",
            external_id = "media1",
            chat_id = self.chat_uuid,
            uploader_user_id = UUID(int = 9),
            message_id = self.message_id,
            size = 1000,
            last_url = "https://old.example/media",
            last_url_until = int(datetime.now().timestamp()),
            extension = "jpg",
            mime_type = "image/jpeg",
        )

    def __save_attachment(
        self,
        attachment: ChatMessageAttachment,
        content: bytes | None = None,
    ) -> ChatMessageAttachment:
        if content is None:
            return attachment

        mime_type, extension = resolve_file_type(
            mime_type = attachment.mime_type,
            extension = attachment.extension,
            uri = attachment.last_url or attachment.uri,
            content = content,
        )
        return replace(
            attachment,
            size = len(content),
            mime_type = mime_type,
            extension = extension,
            last_url = self.stored_media_url,
            last_url_until = None,
        )

    @staticmethod
    def __fail_attachment_save_for_content(
        attachment: ChatMessageAttachment,
        content: bytes | None = None,
    ) -> ChatMessageAttachment:
        if content is not None:
            raise InternalError("Upload failed", ATTACHMENT_STORAGE_FAILED)
        return attachment

    def test_send_text_message(self):
        text = "test message"

        result = self.sdk.send_text_message(chat_id = self.chat_id, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.whatsapp_bot_api.send_text_message.assert_called_once_with(
            recipient_id = str(self.chat_id),
            text = text,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.text, text)
        self.assertEqual(result.chat_id, self.chat_uuid)

    @patch("requests.get")
    def test_send_photo(self, mock_requests_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"\xFF\xD8\xFF\xE0"  # JPEG magic bytes
        mock_requests_get.return_value = mock_response
        photo_url = "http://test.com/photo.jpg"
        caption = "test photo"

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
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)

    @patch("requests.get")
    def test_send_document(self, mock_requests_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4"  # PDF magic bytes
        mock_requests_get.return_value = mock_response
        doc_url = "http://test.com/doc.pdf"
        caption = "test document"

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

    def test_refresh_attachments_by_ids(self):
        attachments = [
            replace(self.attachment, id = "id1"),
            replace(self.attachment, id = "id2"),
        ]
        self.mock_di.chat_message_attachment_repo.get.side_effect = attachments

        with patch.object(WhatsAppBotSDK, "refresh_attachment", side_effect = attachments) as mock_refresh:
            result = self.sdk.refresh_attachments_by_ids(["id1", "id2"])

        self.assertEqual(result, attachments)
        self.assertEqual(mock_refresh.call_count, 2)

    def test_refresh_attachments_by_ids_missing_attachment(self):
        self.mock_di.chat_message_attachment_repo.get.return_value = None

        with self.assertRaises(NotFoundError):
            self.sdk.refresh_attachments_by_ids(["missing"])

    def test_refresh_attachment_fresh_data_skips_api(self):
        attachment = replace(
            self.attachment,
            last_url_until = int(datetime.now().timestamp()) + 3600,
        )

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result, attachment)
        self.mock_di.whatsapp_bot_api.get_media_info.assert_not_called()
        self.mock_chat_message_attachment_service.save.assert_called_once_with(attachment)

    def test_refresh_attachment_no_external_id_error(self):
        attachment = replace(
            self.attachment,
            external_id = None,
            last_url = None,
            last_url_until = None,
        )

        with self.assertRaises(InternalError):
            self.sdk.refresh_attachment(attachment)

    def test_refresh_attachment_missing_media_info_error(self):
        self.mock_di.whatsapp_bot_api.get_media_info.return_value = None

        with self.assertRaises(ExternalServiceError):
            self.sdk.refresh_attachment(self.attachment)

    def test_refresh_attachment_missing_media_content_error(self):
        self.mock_di.whatsapp_bot_api.get_media_info.return_value = MediaInfo(
            id = self.attachment.external_id,
            url = "https://whatsapp.example/media",
        )
        self.mock_di.whatsapp_bot_api.download_media_bytes.return_value = None

        with self.assertRaises(ExternalServiceError):
            self.sdk.refresh_attachment(self.attachment)

    def test_refresh_attachment_updates_and_stores_media(self):
        media_info = MediaInfo(
            id = self.attachment.external_id,
            url = "https://whatsapp.example/media",
            mime_type = "image/png",
            file_size = 2000,
        )
        self.mock_di.whatsapp_bot_api.get_media_info.return_value = media_info
        media_bytes = b"i" * media_info.file_size
        self.mock_di.whatsapp_bot_api.download_media_bytes.return_value = media_bytes

        result = self.sdk.refresh_attachment(self.attachment)

        self.assertEqual(result.id, self.attachment.id)
        self.assertEqual(result.size, media_info.file_size)
        self.assertEqual(result.extension, "png")
        self.assertEqual(result.mime_type, media_info.mime_type)
        self.assertEqual(result.last_url, self.stored_media_url)
        self.assertIsNone(result.last_url_until)
        self.assertEqual(self.attachment.last_url, "https://old.example/media")
        self.mock_chat_message_attachment_service.save.assert_called_once()
        stored_attachment, stored_content = self.mock_chat_message_attachment_service.save.call_args.args
        self.assertEqual(stored_attachment.id, self.attachment.id)
        self.assertIsNone(stored_attachment.extension)
        self.assertEqual(stored_content, media_bytes)

    @patch("features.chat.whatsapp.sdk.whatsapp_bot_sdk.requests.get")
    def test_store_sent_media_detects_and_stores_format(self, mock_requests):
        mock_requests.return_value = Mock(
            status_code = 200,
            content = b"\x89PNG\r\n\x1a\ncontent",
        )

        result = self.sdk._WhatsAppBotSDK__store_attachment_for_sent_media(
            message_id = self.message_id,
            chat_id = self.chat_uuid,
            media_url = "https://source.example/media",
        )

        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, "png")
        self.assertEqual(result.last_url, self.stored_media_url)
        self.mock_chat_message_attachment_service.save.assert_called_once()
        stored_attachment, stored_content = self.mock_chat_message_attachment_service.save.call_args.args
        self.assertEqual(len(stored_attachment.id), 8)
        self.assertEqual(stored_attachment.external_id, self.message_id)
        self.assertIsNone(stored_attachment.extension)
        self.assertEqual(stored_content, mock_requests.return_value.content)

    def test_refresh_attachment_keeps_storage_backed_attachment(self):
        attachment = replace(
            self.attachment,
            last_url = "s3://the-agent/chats/chat-id/attachments/attachment-id",
            last_url_until = None,
        )
        self.mock_chat_message_attachment_service.is_own_storage_uri.return_value = True

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result, attachment)
        self.mock_di.whatsapp_bot_api.get_media_info.assert_not_called()
        self.mock_chat_message_attachment_service.save.assert_not_called()

    @patch("features.chat.whatsapp.sdk.whatsapp_bot_sdk.requests.get")
    def test_store_sent_media_fails_when_download_fails(self, mock_requests):
        mock_requests.return_value = Mock(status_code = 404)

        with self.assertRaises(ExternalServiceError):
            self.sdk._WhatsAppBotSDK__store_attachment_for_sent_media(
                message_id = self.message_id,
                chat_id = self.chat_uuid,
                media_url = "https://source.example/media",
            )

        self.mock_chat_message_attachment_service.save.assert_not_called()

    @patch("features.chat.whatsapp.sdk.whatsapp_bot_sdk.requests.get")
    def test_store_sent_media_fails_when_storage_fails(self, mock_requests):
        mock_requests.return_value = Mock(
            status_code = 200,
            content = b"\x89PNG\r\n\x1a\ncontent",
        )
        self.mock_chat_message_attachment_service.save.side_effect = self.__fail_attachment_save_for_content
        media_url = "https://source.example/media"

        with self.assertRaises(InternalError):
            self.sdk._WhatsAppBotSDK__store_attachment_for_sent_media(
                message_id = self.message_id,
                chat_id = self.chat_uuid,
                media_url = media_url,
            )

        self.mock_chat_message_attachment_service.save.assert_called_once()

    def test_send_button_link(self):
        link_url = "https://test.com"

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

    def test_store_api_response_creates_domain_message(self):
        result = self.sdk._WhatsAppBotSDK__store_api_response_as_message(
            self.api_response,
            text = "test",
            recipient_id = self.chat_id,
        )
        self.assertIsInstance(result, ChatMessage)
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)
        self.assertEqual(result.text, "test")

    def test_store_api_response_chat_not_found(self):
        self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = None
        with self.assertRaises(NotFoundError):
            self.sdk._WhatsAppBotSDK__store_api_response_as_message(
                self.api_response,
                text = "test",
                recipient_id = "unknown",
            )
