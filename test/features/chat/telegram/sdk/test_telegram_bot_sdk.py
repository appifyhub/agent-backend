from datetime import datetime
from typing import cast
from unittest import TestCase

from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from stubs import domain, external
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.integrations.integration_config import THE_AGENT


class TelegramBotSDKTest(TestCase):

    di: DI
    sdk: TelegramBotSDK
    api: FakeTelegramBotAPI
    attachments: ChatAttachmentService
    messages: ChatMessageRepository

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.attachments = self.di.chat_attachment_service
        self.messages = self.di.chat_message_repo
        self.sdk = self.di.telegram_bot_sdk

    def test_send_text_message(self):
        chat = domain.chat_config()
        text = "test message"

        result = self.sdk.send_text_message(chat_config = chat, text = text)

        self.assertEqual(self.api.get_sent_message(result.message_id), {
            "chat_id": chat.external_id,
            "text": text,
            "parse_mode": "markdown",
            "disable_notification": False,
            "link_preview_options": None,
        })
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.author_id, THE_AGENT.id)
        self.assertEqual(result.sent_at, datetime.fromtimestamp(external.telegram_message().date))
        self.assertEqual(result.text, text)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_photo(self):
        attachment = domain.chat_attachment(id = "local123", mime_type = "image/png")
        chat = domain.chat_config()

        result = self.sdk.send_photo(chat_config = chat, attachment = attachment, caption = "test photo")

        sent = self.api.get_sent_message(result.message_id)
        self.assertTrue(self.attachments.is_own_public_url(sent.pop("photo_url")))
        self.assertEqual(sent, {
            "chat_id": chat.external_id,
            "caption": "test photo",
            "parse_mode": "markdown",
            "disable_notification": False,
        })
        self.assertEqual(result.text, "test photo\n\n📎 [ local123 (image/png) ]")
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_document(self):
        attachment = domain.chat_attachment(id = "local456", mime_type = None)
        chat = domain.chat_config()

        result = self.sdk.send_document(chat_config = chat, attachment = attachment, caption = "test document")

        sent = self.api.get_sent_message(result.message_id)
        self.assertTrue(self.attachments.is_own_public_url(sent.pop("document_url")))
        self.assertEqual(sent, {
            "chat_id": chat.external_id,
            "filename": None,
            "content": None,
            "caption": "test document",
            "parse_mode": "markdown",
            "thumbnail": None,
            "disable_notification": False,
        })
        self.assertEqual(result.text, "test document\n\n📎 [ local456 ]")
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_video(self):
        attachment = domain.chat_attachment(id = "local789", extension = "mp4", mime_type = "video/mp4")
        content = external.video_bytes()
        self.di.attachment_storage.put(attachment, content)
        chat = domain.chat_config()
        result = self.sdk.send_video(chat_config = chat, attachment = attachment, caption = "test video")

        self.assertEqual(self.api.get_sent_message(result.message_id), {
            "chat_id": chat.external_id,
            "content": content,
            "metadata": domain.video_metadata(
                size_bytes = len(content), audio_codecs = (), audio_stream_count = 0,
                width = 160, height = 90, duration_seconds = 0.2,
            ),
            "caption": "test video",
            "parse_mode": "markdown",
            "disable_notification": False,
        })
        self.assertEqual(result.text, "test video\n\n📎 [ local789 (video/mp4) ]")
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_video_document_uses_stored_bytes_and_attachment_filename(self):
        attachment = domain.chat_attachment(id = "local-video", extension = "mp4", mime_type = "video/mp4")
        self.di.attachment_storage.put(attachment, b"video content")
        chat = domain.chat_config()

        result = self.sdk.send_document(chat_config = chat, attachment = attachment)

        sent = self.api.get_sent_message(result.message_id)
        self.assertEqual(sent["content"], b"video content")
        self.assertEqual(sent["filename"], "local-video.mp4")
        self.assertIsNone(sent["document_url"])
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)

    def test_set_status_typing(self):
        chat_id = domain.chat_config().external_id

        self.sdk.set_status_typing(chat_id)

        self.assertEqual(self.api.statuses[chat_id], "typing")

    def test_set_status_uploading_image(self):
        chat_id = domain.chat_config().external_id

        self.sdk.set_status_uploading_image(chat_id)

        self.assertEqual(self.api.statuses[chat_id], "upload_photo")

    def test_set_reaction(self):
        chat_id = domain.chat_config().external_id
        message_id = external.telegram_message().message_id

        self.sdk.set_reaction(chat_id, message_id, "👍")

        self.assertEqual(self.api.reactions[(chat_id, str(message_id))], "👍")

    def test_send_button_link(self):
        link_url = "https://test.example.com/settings/key123"
        chat = domain.chat_config()
        for button_text in ("⚙️", None, "test"):
            with self.subTest(button_text = button_text):
                if button_text is None:
                    result = self.sdk.send_button_link(chat_config = chat, link_url = link_url)
                else:
                    result = self.sdk.send_button_link(chat_config = chat, link_url = link_url, button_text = button_text)

                self.assertEqual(self.api.get_sent_message(result.message_id), {
                    "chat_id": chat.external_id,
                    "link_url": link_url,
                    "button_text": button_text or "⚙️",
                })
                label = button_text or "⚙️"
                self.assertEqual(result.text, f"{label} test...123")
                self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_get_chat_member(self):
        chat_id = domain.chat_config().external_id
        member = external.telegram_chat_member()
        user_id = str(member.user.id)
        self.api.members[(chat_id, user_id)] = member

        result = self.sdk.get_chat_member(chat_id, user_id)

        self.assertEqual(result, member)
