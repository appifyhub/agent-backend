import asyncio
from datetime import datetime
from typing import cast
from unittest import TestCase
from uuid import UUID

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.whatsapp.whatsapp_update_responder import _ingest_update, respond_to_update
from features.users.user import User
from util.config import config


class WhatsAppUpdateResponderTest(TestCase):

    di: DI
    api: FakeWhatsAppBotAPI
    model: FakeChatModel
    author: User
    chat: ChatConfig

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.author = self.di.user_repo.save(domain.user(whatsapp_user_id = "1"))
        self.chat = self.di.chat_config_repo.save(domain.chat_config(
            external_id = "1",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        ))
        self.api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(domain.configured_tool(), max_tokens = 500))
        self.addCleanup(setattr, config, "chat_burst_quiet_period_s", config.chat_burst_quiet_period_s)
        config.chat_burst_quiet_period_s = 0

    def test_photo_and_prompt_deliveries_schedule_same_author_bursts(self):
        self.api.downloads["photo"] = b"image content"
        update = external.whatsapp_update(entry = [external.whatsapp_entry(changes = [external.whatsapp_change(
            value = external.whatsapp_value(messages = [
                external.whatsapp_message(
                    id = "photo-message",
                    type = "image",
                    text = None,
                    image = external.whatsapp_media_attachment(id = "photo"),
                    **{"from": "1"},
                ),
                external.whatsapp_message(
                    id = "prompt-message",
                    text = external.whatsapp_text(body = "Describe these"),
                    **{"from": "1"},
                ),
            ]),
        )])])

        outcome = _ingest_update(update)

        self.assertEqual([burst.message_count for burst in outcome.scheduled_bursts], [1, 2])
        self.assertEqual([burst.chat_id for burst in outcome.scheduled_bursts], [self.chat.chat_id, self.chat.chat_id])
        self.assertEqual([burst.author_id for burst in outcome.scheduled_bursts], [self.author.id, self.author.id])
        self.assertFalse(outcome.processed)

    def test_different_chats_schedule_independent_bursts(self):
        other_author = self.di.user_repo.save(domain.user(
            id = UUID("33333333-3333-4333-8333-b33333333333"),
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "2",
            connect_key = "OTHER-USER",
        ))
        update = external.whatsapp_update(entry = [external.whatsapp_entry(changes = [external.whatsapp_change(
            value = external.whatsapp_value(messages = [
                external.whatsapp_message(id = "first", **{"from": "1"}),
                external.whatsapp_message(id = "second", **{"from": "2"}),
            ]),
        )])])

        outcome = _ingest_update(update)

        self.assertEqual([burst.message_count for burst in outcome.scheduled_bursts], [1, 1])
        self.assertEqual([burst.author_id for burst in outcome.scheduled_bursts], [self.author.id, other_author.id])
        self.assertNotEqual(outcome.scheduled_bursts[0].chat_id, outcome.scheduled_bursts[1].chat_id)

    def test_command_does_not_extend_conversational_burst(self):
        update = external.whatsapp_update(entry = [external.whatsapp_entry(changes = [external.whatsapp_change(
            value = external.whatsapp_value(messages = [
                external.whatsapp_message(
                    id = "command",
                    text = external.whatsapp_text(body = "/help"),
                    **{"from": "1"},
                ),
                external.whatsapp_message(
                    id = "prompt",
                    text = external.whatsapp_text(body = "Hello"),
                    **{"from": "1"},
                ),
            ]),
        )])])

        outcome = _ingest_update(update)

        self.assertEqual(len(outcome.scheduled_bursts), 1)
        self.assertEqual(outcome.scheduled_bursts[0].message_count, 1)
        self.assertEqual(len(self.api.get_sent_messages("1")), 1)
        self.assertEqual(self.api.get_sent_messages("1")[0]["text"], "⚙️ https://example.com/short")
        self.assertEqual(self.model.prompts, [])

    def test_async_responder_processes_every_scheduled_burst(self):
        self.di.user_repo.save(domain.user(
            id = UUID("33333333-3333-4333-8333-b33333333333"),
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "2",
            connect_key = "OTHER-USER",
        ))
        self.model.responses.extend([
            external.ai_message(content = "First reply"),
            external.ai_message(content = "Second reply"),
        ])
        update = external.whatsapp_update(entry = [external.whatsapp_entry(changes = [external.whatsapp_change(
            value = external.whatsapp_value(messages = [
                external.whatsapp_message(
                    id = "first",
                    timestamp = str(int(datetime.now().timestamp())),
                    **{"from": "1"},
                ),
                external.whatsapp_message(
                    id = "second",
                    timestamp = str(int(datetime.now().timestamp())),
                    **{"from": "2"},
                ),
            ]),
        )])])

        result = asyncio.run(respond_to_update(update))

        self.assertTrue(result)
        first = self.api.get_sent_messages("1")
        second = self.api.get_sent_messages("2")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertCountEqual([message["text"] for message in first + second], ["First reply", "Second reply"])
        self.assertEqual(self.api.read_messages, {"first", "second"})
