from typing import cast
from unittest import TestCase

from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK
from features.integrations.integration_config import THE_AGENT


class WhatsAppBotSDKTest(TestCase):

    di: DI
    sdk: WhatsAppBotSDK
    api: FakeWhatsAppBotAPI
    attachments: ChatAttachmentService
    messages: ChatMessageRepository

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.attachments = self.di.chat_attachment_service
        self.messages = self.di.chat_message_repo
        self.sdk = self.di.whatsapp_bot_sdk

    def test_send_text_message(self):
        chat = domain.chat_config()

        result = self.sdk.send_text_message(chat_config = chat, text = "test message")

        self.assertEqual(self.api.get_sent_message(result.message_id), {
            "recipient_id": chat.external_id,
            "text": "test message",
        })
        self.assertEqual(result.text, "test message")
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_successful_send_charges_invoker_for_delivery(self):
        payer = self.di.user_repo.save(domain.user(
            whatsapp_user_id = "15551234567",
            credit_balance = 10.0,
        ))
        chat = self.di.chat_config_repo.save(domain.chat_config(
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = payer.whatsapp_user_id,
            is_private = True,
        ))
        self.di.chat_membership_repo.save(domain.chat_membership(
            user_id = payer.id,
            chat_id = chat.chat_id,
        ))
        self.di.inject_invoker(payer)
        price = self.di.messaging_price_service.get(chat.chat_type, payer.whatsapp_user_id or "")

        self.sdk.send_text_message(chat, "test message")

        self.assertAlmostEqual(self.di.user_repo.get(payer.id).credit_balance, 10.0 - price)
        records = self.di.usage_record_repo.get_by_user(payer.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].counterpart_id, payer.id)
        self.assertEqual(records[0].chat_id, chat.chat_id)
        self.assertEqual(records[0].api_call_cost_credits, price)
        self.assertFalse(records[0].is_delivery_reconciled)

    def test_send_photo(self):
        chat = domain.chat_config()
        attachment = domain.chat_attachment(id = "local123", mime_type = None)

        result = self.sdk.send_photo(chat_config = chat, attachment = attachment, caption = "test photo")

        sent = self.api.get_sent_message(result.message_id)
        self.assertTrue(self.attachments.is_own_public_url(sent.pop("image_url")))
        self.assertEqual(sent, {
            "recipient_id": chat.external_id,
            "caption": "test photo",
        })
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(result.text, "test photo\n\n📎 [ local123 ]")
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_document(self):
        chat = domain.chat_config()
        attachment = domain.chat_attachment(id = "local456", extension = "pdf", mime_type = None)

        result = self.sdk.send_document(chat_config = chat, attachment = attachment, caption = "test document")

        sent = self.api.get_sent_message(result.message_id)
        self.assertTrue(self.attachments.is_own_public_url(sent.pop("document_url")))
        self.assertEqual(sent, {
            "recipient_id": chat.external_id,
            "caption": "test document",
            "filename": "local456.pdf",
        })
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(result.text, "test document\n\n📎 [ local456 ]")
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_send_video(self):
        chat = domain.chat_config()
        attachment = domain.chat_attachment(id = "local789", mime_type = "video/mp4")

        result = self.sdk.send_video(chat_config = chat, attachment = attachment, caption = "test video")

        sent = self.api.get_sent_message(result.message_id)
        self.assertTrue(self.attachments.is_own_public_url(sent.pop("video_url")))
        self.assertEqual(sent, {
            "recipient_id": chat.external_id,
            "caption": "test video",
        })
        self.assertEqual(self.attachments.get(attachment.id).message_id, result.message_id)
        self.assertEqual(result.text, "test video\n\n📎 [ local789 (video/mp4) ]")
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_set_reaction(self):
        chat_id = domain.chat_config().external_id
        message_id = external.whatsapp_sent_message_response().id

        self.sdk.set_reaction(chat_id, message_id, "👍")

        self.assertEqual(self.api.reactions[(chat_id, message_id)], "👍")

    def test_send_button_link(self):
        link_url = "https://test.example.com/settings/key123"
        chat = domain.chat_config()
        for button_text in ("⚙️", None, "test"):
            with self.subTest(button_text = button_text):
                if button_text is None:
                    result = self.sdk.send_button_link(chat_config = chat, link_url = link_url)
                else:
                    result = self.sdk.send_button_link(chat_config = chat, link_url = link_url, button_text = button_text)

                label = button_text or "⚙️"
                self.assertEqual(self.api.get_sent_message(result.message_id), {
                    "recipient_id": chat.external_id,
                    "text": f"{label} {link_url}",
                })
                self.assertEqual(result.text, f"{label} test...123")
                self.assertEqual(result.chat_id, chat.chat_id)
                self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)

    def test_store_api_response_creates_domain_message(self):
        chat = domain.chat_config()

        result = self.sdk.send_text_message(chat, "test")

        self.assertEqual(result.author_id, THE_AGENT.id)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.text, "test")
        self.assertEqual(self.messages.get(chat.chat_id, result.message_id), result)
