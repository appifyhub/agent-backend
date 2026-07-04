import unittest
from dataclasses import replace
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import UUID

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.message.chat_message import ChatMessage
from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from util.errors import InternalError, NotFoundError


class TelegramBotSDKTest(unittest.TestCase):

    sdk: TelegramBotSDK
    mock_di: DI

    def setUp(self):
        # Create mock DI with all required dependencies
        self.mock_di = Mock(spec = DI)

        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_api = Mock(spec = TelegramBotAPI)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_data_resolver = Mock(spec = TelegramDataResolver)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_domain_mapper = Mock(spec = TelegramDomainMapper)
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_attachment_repo = Mock()
        self.mock_di.chat_message_attachment_repo.save.side_effect = lambda attachment: attachment

        self.sdk = TelegramBotSDK(self.mock_di)

        self.user_id = "001"
        self.chat_id = "123"
        self.message_id = "456"
        self.api_response = {
            "result": {
                "message_id": self.message_id,
                "chat": {
                    "id": self.chat_id,
                    "type": "private",  # Required field
                },
                "date": 1234567890,  # Required field
                "text": "test message",
            },
        }
        self.mock_di.telegram_bot_api.send_text_message.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_photo.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_document.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_button_link.return_value = self.api_response
        self.mock_di.telegram_bot_api.get_chat_member.return_value = self.api_response

        self.attachment = ChatMessageAttachment(
            id = "short123",
            external_id = "telegram_file_456",
            chat_id = UUID(int = 1),
            message_id = "msg_123",
            size = 1000,
            last_url = "http://old.url",
            last_url_until = int(datetime.now().timestamp()),
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        self.api_file_info = Mock(
            file_size = 2000,
            file_path = "files/test.png",
        )
        self.mock_di.telegram_bot_api.get_file_info.return_value = self.api_file_info

    @patch.object(TelegramDomainMapper, "map_update")
    def test_send_text_message(self, mock_map_update):
        text = "test message"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.mock_di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],
        )

        result = self.sdk.send_text_message(chat_id = self.chat_id, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_text_message.assert_called_once_with(
            chat_id = self.chat_id,
            text = text,
            parse_mode = "markdown",
            disable_notification = False,
            link_preview_options = None,
        )
        self.assertEqual(result, expected_message)

    @patch.object(TelegramDomainMapper, "map_update")
    def test_send_photo(self, mock_map_update):
        photo_url = "http://test.com/photo.jpg"
        caption = "test photo"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.mock_di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],
        )

        result = self.sdk.send_photo(
            chat_id = self.chat_id,
            photo_url = photo_url,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_photo.assert_called_once_with(
            chat_id = self.chat_id,
            photo_url = photo_url,
            caption = caption,
            parse_mode = "markdown",
            disable_notification = False,
        )
        self.assertEqual(result, expected_message)

    @patch.object(TelegramDomainMapper, "map_update")
    def test_send_document(self, mock_map_update):
        doc_url = "http://test.com/doc.pdf"
        caption = "test document"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.mock_di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            message = expected_message,
            attachments = [Mock(spec = ChatMessageAttachment)],  # Add at least one attachment
        )

        result = self.sdk.send_document(
            chat_id = self.chat_id,
            document_url = doc_url,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_document.assert_called_once_with(
            chat_id = self.chat_id,
            document_url = doc_url,
            caption = caption,
            parse_mode = "markdown",
            thumbnail = None,
            disable_notification = False,
        )
        self.assertEqual(result, expected_message)

    def test_set_status_typing(self):
        self.sdk.set_status_typing(self.chat_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_status_typing.assert_called_once_with(self.chat_id)

    def test_set_status_uploading_image(self):
        self.sdk.set_status_uploading_image(self.chat_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_status_uploading_image.assert_called_once_with(self.chat_id)

    def test_set_reaction(self):
        reaction = "👍"
        self.sdk.set_reaction(self.chat_id, self.message_id, reaction)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_reaction.assert_called_once_with(
            chat_id = self.chat_id,
            message_id = self.message_id,
            reaction = reaction,
        )

    @patch.object(TelegramDomainMapper, "map_update")
    def test_send_button_link(self, mock_map_update):
        link_url = "https://test.com"
        expected_message = Mock(spec = ChatMessage)
        mock_map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.mock_di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
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
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "⚙️")
        self.assertEqual(result, expected_message)

        # Test default-to-settings button
        result = self.sdk.send_button_link(
            chat_id = self.chat_id,
            link_url = link_url,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "⚙️")
        self.assertEqual(result, expected_message)

        # Test custom button text
        result = self.sdk.send_button_link(
            chat_id = self.chat_id,
            link_url = link_url,
            button_text = "test",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "test")
        self.assertEqual(result, expected_message)

    def test_get_chat_member(self):
        self.sdk.get_chat_member(self.chat_id, self.user_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.get_chat_member.assert_called_once_with(self.chat_id, self.user_id)

    def test_store_api_response_mapping_failure(self):
        self.mock_di.telegram_domain_mapper.map_update.return_value = None

        with self.assertRaises(InternalError) as context:
            # noinspection PyUnresolvedReferences
            self.sdk._TelegramBotSDK__store_api_response_as_message(self.api_response)
        self.assertTrue("domain mapping failed" in str(context.exception))

    @patch.object(TelegramDomainMapper, "map_update")
    def test_store_api_response_resolution_failure(self, mock_map_update):
        mock_map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.mock_di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            message = None,
            attachments = None,
        )

        with self.assertRaises(InternalError) as context:
            # noinspection PyUnresolvedReferences
            self.sdk._TelegramBotSDK__store_api_response_as_message(self.api_response)
        self.assertTrue("data resolution failed" in str(context.exception))

    def test_refresh_attachments_by_ids_empty_list(self):
        result = self.sdk.refresh_attachments_by_ids(attachment_ids = [])

        self.assertEqual(result, [])

    def test_refresh_attachments_by_ids_with_attachments(self):
        attachments = [
            replace(self.attachment, id = "short1", external_id = "ext1", message_id = "msg1"),
            replace(self.attachment, id = "short2", external_id = "ext2", message_id = "msg2"),
        ]
        self.mock_di.chat_message_attachment_repo.get.side_effect = attachments

        with patch.object(TelegramBotSDK, "refresh_attachment", side_effect = attachments) as mock_refresh:
            result = self.sdk.refresh_attachments_by_ids(attachment_ids = ["short1", "short2"])

        self.assertEqual(result, attachments)
        self.assertEqual(mock_refresh.call_count, 2)

    def test_refresh_attachments_by_ids_missing_attachment(self):
        self.mock_di.chat_message_attachment_repo.get.return_value = None

        with self.assertRaises(NotFoundError):
            self.sdk.refresh_attachments_by_ids(attachment_ids = ["missing"])

    def test_refresh_attachment_updates_stale_data(self):
        result = self.sdk.refresh_attachment(self.attachment)

        self.assertEqual(result.id, self.attachment.id)
        self.assertEqual(result.external_id, self.attachment.external_id)
        self.assertEqual(result.size, self.api_file_info.file_size)
        self.assertTrue(result.last_url.endswith(self.api_file_info.file_path))
        self.assertGreater(result.last_url_until, self.attachment.last_url_until)
        self.mock_di.telegram_bot_api.get_file_info.assert_called_once_with(self.attachment.external_id)
        self.mock_di.chat_message_attachment_repo.save.assert_called_once_with(result)
        self.assertEqual(self.attachment.last_url, "http://old.url")

    def test_refresh_attachment_fresh_data_skips_api(self):
        attachment = replace(
            self.attachment,
            last_url_until = int(datetime.now().timestamp()) + 3600,
        )

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result, attachment)
        self.mock_di.telegram_bot_api.get_file_info.assert_not_called()
        self.mock_di.chat_message_attachment_repo.save.assert_called_once_with(attachment)

    def test_refresh_attachment_no_external_id_error(self):
        attachment = replace(
            self.attachment,
            external_id = None,
            last_url = None,
            last_url_until = None,
        )

        with self.assertRaises(InternalError) as context:
            self.sdk.refresh_attachment(attachment)

        self.assertIn("No external ID provided", str(context.exception))

    def test_refresh_attachment_extension_and_mime_inference(self):
        attachment = replace(
            self.attachment,
            extension = None,
            mime_type = None,
            last_url = None,
            last_url_until = None,
        )
        self.api_file_info.file_path = "documents/photo.png"

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result.extension, "png")
        self.assertEqual(result.mime_type, "image/png")

    def test_refresh_attachment_trusts_mime_type_before_file_path(self):
        attachment = replace(
            self.attachment,
            extension = None,
            mime_type = "application/pdf",
            last_url = None,
            last_url_until = None,
        )
        self.api_file_info.file_path = "documents/photo.png"

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result.extension, "pdf")
        self.assertEqual(result.mime_type, "application/pdf")

    def test_refresh_attachment_infers_missing_mime_type_from_extension(self):
        attachment = replace(
            self.attachment,
            extension = "png",
            mime_type = None,
            last_url = None,
            last_url_until = None,
        )
        self.api_file_info.file_path = "documents/photo.png"

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result.extension, "png")
        self.assertEqual(result.mime_type, "image/png")

    @patch("features.chat.telegram.sdk.telegram_bot_sdk.requests.get")
    def test_refresh_attachment_does_not_detect_image_format_when_mime_type_exists(self, mock_requests):
        attachment = replace(
            self.attachment,
            extension = None,
            mime_type = "application/octet-stream",
        )
        self.api_file_info.file_path = None

        result = self.sdk.refresh_attachment(attachment)

        self.assertIsNone(result.extension)
        self.assertEqual(result.mime_type, "application/octet-stream")
        mock_requests.assert_not_called()

    def test_refresh_attachment_instances(self):
        attachments = [
            replace(self.attachment, id = "id1"),
            replace(self.attachment, id = "id2"),
        ]

        with patch.object(TelegramBotSDK, "refresh_attachment", side_effect = attachments) as mock_refresh:
            result = self.sdk.refresh_attachment_instances(attachments = attachments)

        self.assertEqual(result, attachments)
        self.assertEqual(mock_refresh.call_count, 2)

    @patch("features.chat.telegram.sdk.telegram_bot_sdk.requests.get")
    def test_refresh_attachment_detects_image_format_when_missing(self, mock_requests):
        mock_response = Mock(status_code = 200, content = b"\x89PNG\r\n\x1a\ncontent")
        mock_requests.return_value = mock_response
        self.api_file_info.file_path = None
        attachment = replace(
            self.attachment,
            extension = None,
            mime_type = None,
        )

        result = self.sdk.refresh_attachment(attachment)

        self.assertEqual(result.extension, "png")
        self.assertEqual(result.mime_type, "image/png")
        mock_requests.assert_called_once_with(attachment.last_url, timeout = 10)

    @patch("features.chat.telegram.sdk.telegram_bot_sdk.requests.get")
    def test_refresh_attachment_handles_image_detection_failure(self, mock_requests):
        mock_requests.side_effect = Exception("Network error")
        self.api_file_info.file_path = None
        attachment = replace(
            self.attachment,
            extension = None,
            mime_type = None,
        )

        result = self.sdk.refresh_attachment(attachment)

        self.assertIsNone(result.extension)
        self.assertIsNone(result.mime_type)
