import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import stubs

from di.di import DI
from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.integrations.integration_config import THE_AGENT


class TelegramBotSDKTest(unittest.TestCase):

    sdk: TelegramBotSDK
    mock_di: DI

    def setUp(self):
        self.mock_di = Mock(spec = DI)

        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_api = Mock(spec = TelegramBotAPI)
        self.mock_chat_attachment_service = Mock()
        self.mock_chat_attachment_service.create_public_url.return_value = stubs.domain.public_attachment()
        self.mock_di.chat_attachment_service = self.mock_chat_attachment_service
        self.mock_di.attachment_storage = Mock()
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = Mock()
        self.mock_di.chat_message_repo.save.side_effect = lambda message: message

        self.sdk = TelegramBotSDK(self.mock_di)
        api_message = stubs.external.telegram_message(text = "test message")
        api_response = {
            "ok": True,
            "result": api_message.model_dump(by_alias = True),
        }
        self.mock_di.telegram_bot_api.send_text_message.return_value = api_response
        self.mock_di.telegram_bot_api.send_photo.return_value = api_response
        self.mock_di.telegram_bot_api.send_document.return_value = api_response
        self.mock_di.telegram_bot_api.send_video.return_value = api_response
        self.mock_di.telegram_bot_api.send_button_link.return_value = api_response
        self.mock_di.telegram_bot_api.get_chat_member.return_value = api_response

    def test_send_text_message(self):
        chat_config = stubs.domain.chat_config()
        text = "test message"

        result = self.sdk.send_text_message(chat_config = chat_config, text = text)

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_text_message.assert_called_once_with(
            chat_id = chat_config.external_id,
            text = text,
            parse_mode = "markdown",
            disable_notification = False,
            link_preview_options = None,
        )
        api_result = self.mock_di.telegram_bot_api.send_text_message.return_value["result"]
        self.assertEqual(result.message_id, str(api_result["message_id"]))
        self.assertEqual(result.chat_id, chat_config.chat_id)
        self.assertEqual(result.author_id, THE_AGENT.id)
        self.assertEqual(result.sent_at, datetime.fromtimestamp(api_result["date"]))
        self.assertEqual(result.text, text)
        self.mock_di.chat_message_repo.save.assert_called_once_with(result)

    def test_send_photo(self):
        caption = "test photo"
        attachment = stubs.domain.chat_attachment(
            id = "local123",
            mime_type = "image/png",
        )
        chat_config = stubs.domain.chat_config()
        public_url = self.mock_chat_attachment_service.create_public_url.return_value.url
        result = self.sdk.send_photo(
            chat_config = chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_photo.assert_called_once_with(
            chat_id = chat_config.external_id,
            photo_url = public_url,
            caption = caption,
            parse_mode = "markdown",
            disable_notification = False,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.assertEqual(result.text, "test photo\n\n📎 [ local123 (image/png) ]")
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)

    def test_send_document(self):
        caption = "test document"
        attachment = stubs.domain.chat_attachment(
            id = "local456",
            mime_type = None,
        )
        chat_config = stubs.domain.chat_config()
        public_url = self.mock_chat_attachment_service.create_public_url.return_value.url
        result = self.sdk.send_document(
            chat_config = chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_document.assert_called_once_with(
            chat_id = chat_config.external_id,
            document_url = public_url,
            caption = caption,
            parse_mode = "markdown",
            thumbnail = None,
            disable_notification = False,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.assertEqual(result.text, "test document\n\n📎 [ local456 ]")
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)

    def test_send_video(self):
        caption = "test video"
        attachment = stubs.domain.chat_attachment(
            id = "local789",
            extension = "mp4",
            mime_type = "video/mp4",
        )
        temporary_path = "/tmp/stored-video.mp4"
        temporary_path_context = MagicMock()
        temporary_path_context.__enter__.return_value = temporary_path
        self.mock_di.attachment_storage.temporary_path.return_value = temporary_path_context
        metadata = stubs.domain.video_metadata()
        with patch(
            "features.chat.telegram.sdk.telegram_bot_sdk.inspect_video",
            return_value = metadata,
        ) as mock_inspect:
            chat_config = stubs.domain.chat_config()
            result = self.sdk.send_video(
                chat_config = chat_config,
                attachment = attachment,
                caption = caption,
            )

        self.mock_di.attachment_storage.temporary_path.assert_called_once_with(attachment)
        mock_inspect.assert_called_once_with(temporary_path)
        self.mock_di.telegram_bot_api.send_video.assert_called_once_with(
            chat_id = chat_config.external_id,
            video_path = temporary_path,
            metadata = metadata,
            caption = caption,
            parse_mode = "markdown",
            disable_notification = False,
        )
        self.assertEqual(result.text, "test video\n\n📎 [ local789 (video/mp4) ]")
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, result.message_id)

    def test_send_video_document_uses_stored_bytes_and_attachment_filename(self):
        attachment = stubs.domain.chat_attachment(
            id = "local-video",
            extension = "mp4",
            mime_type = "video/mp4",
        )
        temporary_path = "/tmp/stored-video.mp4"
        temporary_path_context = MagicMock()
        temporary_path_context.__enter__.return_value = temporary_path
        self.mock_di.attachment_storage.temporary_path.return_value = temporary_path_context
        chat_config = stubs.domain.chat_config()
        self.sdk.send_document(
            chat_config = chat_config,
            attachment = attachment,
        )

        self.mock_di.attachment_storage.temporary_path.assert_called_once_with(attachment)
        call_kwargs = self.mock_di.telegram_bot_api.send_document.call_args.kwargs
        self.assertEqual(call_kwargs["document_path"], temporary_path)
        self.assertEqual(call_kwargs["filename"], "local-video.mp4")
        self.mock_chat_attachment_service.create_public_url.assert_not_called()

    def test_set_status_typing(self):
        chat_id = stubs.domain.chat_config().external_id

        self.sdk.set_status_typing(chat_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_status_typing.assert_called_once_with(chat_id)

    def test_set_status_uploading_image(self):
        chat_id = stubs.domain.chat_config().external_id

        self.sdk.set_status_uploading_image(chat_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_status_uploading_image.assert_called_once_with(chat_id)

    def test_set_reaction(self):
        chat_id = stubs.domain.chat_config().external_id
        message_id = stubs.external.telegram_message().message_id
        reaction = "👍"

        self.sdk.set_reaction(chat_id, message_id, reaction)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.set_reaction.assert_called_once_with(
            chat_id = chat_id,
            message_id = message_id,
            reaction = reaction,
        )

    def test_send_button_link(self):
        link_url = "https://test.example.com/settings/key123"

        chat_config = stubs.domain.chat_config()
        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
            button_text = "⚙️",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(
            chat_config.external_id,
            link_url,
            "⚙️",
        )
        self.assertEqual(result.text, "⚙️ test...123")

        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(
            chat_config.external_id,
            link_url,
            "⚙️",
        )
        self.assertEqual(result.text, "⚙️ test...123")

        result = self.sdk.send_button_link(
            chat_config = chat_config,
            link_url = link_url,
            button_text = "test",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(
            chat_config.external_id,
            link_url,
            "test",
        )
        self.assertEqual(result.text, "test test...123")

    def test_get_chat_member(self):
        chat_id = stubs.domain.chat_config().external_id
        user_id = "001"

        self.sdk.get_chat_member(chat_id, user_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.get_chat_member.assert_called_once_with(chat_id, user_id)
