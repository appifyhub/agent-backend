import unittest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.chat_image_edit_service import ChatImageEditService
from util.config import config


class ChatImageEditServiceTest(unittest.TestCase):

    def setUp(self):
        config.web_timeout_s = 1
        self.attachment_ids = ["attachment1", "attachment2"]
        self.operation_guidance = None
        self.mock_di = MagicMock()
        self.mock_platform_sdk = MagicMock()
        self.mock_di.platform_bot_sdk = MagicMock(return_value = self.mock_platform_sdk)
        self.mock_di.chat_message_attachment_service = MagicMock()
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = []
        mock_chat = MagicMock()
        mock_chat.external_id = "test_chat_id"
        mock_chat.chat_type = ChatConfigDB.ChatType.telegram
        mock_chat.media_mode = ChatConfigDB.MediaMode.all
        self.mock_di.require_invoker_chat = MagicMock(return_value = mock_chat)
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        self.mock_di.tool_choice_resolver = MagicMock()
        self.mock_di.image_editor = MagicMock()

        self.attachment = ChatMessageAttachment(
            id = "attachment1",
            external_id = "telegram_file_1",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            message_id = "message1",
            size = 1024,
            last_url = "http://test.com/image.png",
            last_url_until = int(datetime.now().timestamp()) + 3600,
            extension = "png",
            mime_type = "image/png",
        )

        self.attachment2 = ChatMessageAttachment(
            id = "attachment2",
            external_id = "telegram_file_2",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            message_id = "message1",
            size = 2048,
            last_url = "http://test.com/image2.png",
            last_url_until = int(datetime.now().timestamp()) + 3600,
            extension = "png",
            mime_type = "image/png",
        )

        self.attachment_no_url = ChatMessageAttachment(
            id = "attachment_no_url",
            external_id = "telegram_file_3",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            message_id = "message1",
            size = 512,
            last_url = None,
            last_url_until = None,
            extension = "png",
            mime_type = "image/png",
        )

        self.url_attachment = ChatMessageAttachment(
            id = "url-attachment",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            last_url = "https://example.com/image.png",
            extension = "png",
            mime_type = "image/png",
        )

    def test_init_success(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment]

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )

        self.assertIsInstance(service, ChatImageEditService)

    def test_execute_edit_image_success_single(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = "http://test.com/edited_image.png"
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.success)
        self.assertEqual(details, [{"url": "http://test.com/edited_image.png", "error": None, "status": "delivered"}])
        self.mock_di.image_editor.assert_called_once_with(
            image_urls = ["http://test.com/image.png"],
            configured_tool = self.mock_di.tool_choice_resolver.require_tool.return_value,
            prompt = "<empty>",
            input_mime_types = ["image/png"],
            aspect_ratio = None,
            output_size = None,
        )
        self.mock_platform_sdk.smart_send_photo.assert_called_once_with(
            media_mode = ChatConfigDB.MediaMode.all,
            chat_id = "test_chat_id",
            photo_url = "http://test.com/edited_image.png",
            thumbnail = "http://test.com/edited_image.png",
        )

    def test_execute_edit_image_success_multi(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment, self.attachment2]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = "http://test.com/edited_image.png"
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.success)
        self.assertEqual(details, [{"url": "http://test.com/edited_image.png", "error": None, "status": "delivered"}])
        self.mock_di.image_editor.assert_called_once_with(
            image_urls = ["http://test.com/image.png", "http://test.com/image2.png"],
            configured_tool = self.mock_di.tool_choice_resolver.require_tool.return_value,
            prompt = "<empty>",
            input_mime_types = ["image/png", "image/png"],
            aspect_ratio = None,
            output_size = None,
        )

    def test_execute_edit_image_partial_some_urls_missing(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment, self.attachment_no_url]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = "http://test.com/edited_image.png"
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.partial)
        self.assertEqual(details, [{"url": "http://test.com/edited_image.png", "error": None, "status": "delivered"}])
        # Only the valid URL is passed to the editor
        self.mock_di.image_editor.assert_called_once_with(
            image_urls = ["http://test.com/image.png"],
            configured_tool = self.mock_di.tool_choice_resolver.require_tool.return_value,
            prompt = "<empty>",
            input_mime_types = ["image/png"],
            aspect_ratio = None,
            output_size = None,
        )

    def test_execute_edit_image_all_urls_missing(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment_no_url]

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.failed)
        self.assertEqual(details, [{"url": None, "error": "No valid attachment URLs found"}])
        self.mock_di.image_editor.assert_not_called()

    def test_execute_edit_image_failed_editor_error(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = None
        mock_editor.error = "Image editing failed"
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.failed)
        self.assertEqual(details, [{"url": None, "error": "Image editing failed"}])
        mock_editor.execute.assert_called_once()
        self.mock_platform_sdk.smart_send_photo.assert_not_called()

    def test_execute_edit_image_failed_no_result(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = None
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.failed)
        self.assertEqual(details, [{"url": None, "error": "Failed to edit images"}])
        self.mock_platform_sdk.smart_send_photo.assert_not_called()

    def test_execute_edit_image_exception(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment]
        mock_editor = MagicMock()
        mock_editor.execute.side_effect = Exception("Test exception")
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = self.attachment_ids,
            urls = None,
            operation_guidance = self.operation_guidance,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.failed)
        self.assertEqual(details, [{"url": None, "error": "Test exception"}])
        self.mock_platform_sdk.smart_send_photo.assert_not_called()

    def test_url_attachment_from_attachment_service_is_edited(self):
        virtual_url = "https://example.com/image.png"
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.url_attachment]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = "http://test.com/edited.png"
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = [],
            urls = [virtual_url],
            operation_guidance = None,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        result, details = service.execute()

        self.assertEqual(result, ChatImageEditService.Result.success)
        call_kwargs = self.mock_di.image_editor.call_args[1]
        self.assertEqual(call_kwargs["image_urls"], [virtual_url])
        self.assertEqual(call_kwargs["input_mime_types"], ["image/png"])

    def test_service_resolved_url_and_db_attachments_are_edited(self):
        virtual_url = "https://example.com/virtual.png"
        url_attachment = ChatMessageAttachment(
            id = "url-attachment",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 9),
            last_url = virtual_url,
            extension = "png",
            mime_type = "image/png",
        )
        self.mock_di.chat_message_attachment_service.resolve_attachments.return_value = [self.attachment, url_attachment]
        mock_editor = MagicMock()
        mock_editor.execute.return_value = "http://test.com/edited.png"
        mock_editor.error = None
        self.mock_di.image_editor.return_value = mock_editor

        service = ChatImageEditService(
            attachment_ids = ["attachment1"],
            urls = [virtual_url],
            operation_guidance = None,
            aspect_ratio = None,
            output_size = None,
            di = self.mock_di,
        )
        service.execute()

        call_kwargs = self.mock_di.image_editor.call_args[1]
        self.assertIn(virtual_url, call_kwargs["image_urls"])
        self.assertIn("http://test.com/image.png", call_kwargs["image_urls"])

    def test_empty_ids_and_no_urls_raises_error(self):
        self.mock_di.chat_message_attachment_service.resolve_attachments.side_effect = Exception("missing attachments")

        with self.assertRaises(Exception):
            ChatImageEditService(
                attachment_ids = [],
                urls = None,
                operation_guidance = None,
                aspect_ratio = None,
                output_size = None,
                di = self.mock_di,
            )
