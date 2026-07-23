import unittest
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
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
        self.mock_di.invoker = SimpleNamespace(id = UUID(int = 9))
        self.stored_media_url = "s3://the-agent/chats/chat-id/attachments/attachment-id"
        self.public_url = "https://agent.example/attachments/public/token"
        self.mock_chat_attachment_service = Mock()
        self.mock_chat_attachment_service.save.side_effect = self.__save_attachment
        self.mock_chat_attachment_service.create_public_url.return_value = SimpleNamespace(url = self.public_url)
        self.mock_di.chat_attachment_service = self.mock_chat_attachment_service
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = Mock()
        self.mock_di.chat_message_repo.save.side_effect = lambda message: message

        self.sdk = TelegramBotSDK(self.mock_di)

        self.user_id = "001"
        self.chat_id = "123"
        self.message_id = "456"
        self.chat_uuid = UUID("12345678-1234-5678-1234-567812345678")
        self.chat_config = ChatConfig(
            chat_id = self.chat_uuid,
            external_id = self.chat_id,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.api_response = {
            "result": {
                "message_id": self.message_id,
                "chat": {
                    "id": self.chat_id,
                    "type": "private",
                },
                "date": 1234567890,
                "text": "test message",
            },
        }
        self.mock_di.telegram_bot_api.send_text_message.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_photo.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_document.return_value = self.api_response
        self.mock_di.telegram_bot_api.send_button_link.return_value = self.api_response
        self.mock_di.telegram_bot_api.get_chat_member.return_value = self.api_response

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
        self.mock_di.telegram_bot_api.send_text_message.assert_called_once_with(
            chat_id = self.chat_id,
            text = text,
            parse_mode = "markdown",
            disable_notification = False,
            link_preview_options = None,
        )
        self.assertEqual(result.message_id, self.message_id)
        self.assertEqual(result.chat_id, self.chat_uuid)
        self.assertEqual(result.author_id, THE_AGENT.id)
        self.assertEqual(result.sent_at, datetime.fromtimestamp(1234567890))
        self.assertEqual(result.text, text)
        self.mock_di.chat_message_repo.save.assert_called_once_with(result)

    def test_send_photo(self):
        caption = "test photo"
        attachment = ChatAttachment(
            id = "local123",
            chat_id = self.chat_uuid,
            uploader_user_id = self.mock_di.invoker.id,
            mime_type = "image/png",
        )

        result = self.sdk.send_photo(
            chat_config = self.chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_photo.assert_called_once_with(
            chat_id = self.chat_id,
            photo_url = self.public_url,
            caption = caption,
            parse_mode = "markdown",
            disable_notification = False,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.assertEqual(result.text, "test photo\n\n📎 [ local123 (image/png) ]")
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, self.message_id)

    def test_send_document(self):
        caption = "test document"
        attachment = ChatAttachment(
            id = "local456",
            chat_id = self.chat_uuid,
            uploader_user_id = self.mock_di.invoker.id,
        )

        result = self.sdk.send_document(
            chat_config = self.chat_config,
            attachment = attachment,
            caption = caption,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_document.assert_called_once_with(
            chat_id = self.chat_id,
            document_url = self.public_url,
            caption = caption,
            parse_mode = "markdown",
            thumbnail = None,
            disable_notification = False,
        )
        self.mock_chat_attachment_service.create_public_url.assert_called_once_with(attachment)
        self.assertEqual(result.text, "test document\n\n📎 [ local456 ]")
        patched_attachment = self.mock_chat_attachment_service.save.call_args.args[0]
        self.assertEqual(patched_attachment.id, attachment.id)
        self.assertEqual(patched_attachment.message_id, self.message_id)

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

    def test_send_button_link(self):
        link_url = "https://test.example.com/settings/key123"

        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
            button_text = "⚙️",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "⚙️")
        self.assertEqual(result.text, "⚙️ test...123")

        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "⚙️")
        self.assertEqual(result.text, "⚙️ test...123")

        result = self.sdk.send_button_link(
            chat_config = self.chat_config,
            link_url = link_url,
            button_text = "test",
        )

        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.send_button_link.assert_called_with(self.chat_id, link_url, "test")
        self.assertEqual(result.text, "test test...123")

    def test_get_chat_member(self):
        self.sdk.get_chat_member(self.chat_id, self.user_id)
        # noinspection PyUnresolvedReferences
        self.mock_di.telegram_bot_api.get_chat_member.assert_called_once_with(self.chat_id, self.user_id)
