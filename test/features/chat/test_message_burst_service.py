import asyncio
from datetime import datetime, timedelta
from typing import cast
from unittest import TestCase
from unittest.mock import patch

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from langchain_core.messages import BaseMessage
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message_burst_service import MessageBurstService
from features.integrations.integrations import resolve_agent_user, resolve_external_handle
from util.config import config


class MessageBurstServiceTest(TestCase):

    di: DI
    service: MessageBurstService
    model: FakeChatModel
    telegram: FakeTelegramBotAPI
    whatsapp: FakeWhatsAppBotAPI
    ingested: IngestedChatMessage

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        author = self.di.user_repo.save(domain.user())
        chat = self.di.chat_config_repo.save(domain.chat_config(is_private = True, external_id = "123"))
        self.di.inject_invoker(author)
        self.di.inject_invoker_chat(chat)
        self.di.chat_membership_repo.save(domain.chat_membership(user_id = author.id, chat_id = chat.chat_id))
        message = self.di.chat_message_repo.save(domain.chat_message(
            chat_id = chat.chat_id,
            author_id = author.id,
            message_id = "message-1",
            sent_at = datetime(2026, 1, 2, 12),
            text = "hello",
            ingestion_order = 1,
        ))
        self.ingested = domain.ingested_chat_message(chat = chat, author = author, message = message, raw_message_text = "hello")
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(domain.configured_tool(), max_tokens = 500))
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.service = self.di.message_burst_service

    def test_explicit_address_ignores_quoted_mentions(self):
        chat_type = ChatConfigDB.ChatType.telegram
        handle = resolve_external_handle(resolve_agent_user(chat_type), chat_type)

        self.assertTrue(self.service.is_explicitly_addressed(f"hello @{handle}", chat_type))
        self.assertFalse(self.service.is_explicitly_addressed(f">> hello @{handle}\nnot addressed", chat_type))

    def test_claimed_message_uses_cutoff_and_aggregate_addressing(self):
        self.ingested.chat.is_private = False
        self.ingested.chat.reply_chance_percent = 0
        self.di.chat_message_repo.save(domain.chat_message(
            chat_id = self.ingested.chat.chat_id,
            author_id = self.ingested.author.id,
            message_id = "newer",
            ingestion_order = 2,
            sent_at = self.ingested.message.sent_at + timedelta(seconds = 1),
            text = "Future message outside this burst",
        ))
        claim = domain.claimed_chat_message_burst(
            chat_id = self.ingested.chat.chat_id,
            author_id = self.ingested.author.id,
            last_message_sent_at = self.ingested.message.sent_at,
            last_message_ingestion_order = self.ingested.message.ingestion_order,
            is_addressed = True,
        )
        self.model.responses.append(external.ai_message(content = "response"))

        result = self.service.process_message(self.ingested, claim = claim)

        self.assertTrue(result)
        self.assertEqual([message["text"] for message in self.telegram.get_sent_messages("123")], ["response"])
        self.assertNotIn("Future message outside this burst", str(self.model.prompts))
        self.assertIn("hello", str(self.model.prompts))

    def test_reaction_response_is_stored_and_sent(self):
        self.model.responses.append(external.ai_message(content = "👍"))

        self.assertTrue(self.service.process_message(self.ingested))

        self.assertEqual(self.telegram.reactions[("123", "message-1")], "👍")
        saved = self.di.chat_message_repo.get(self.ingested.chat.chat_id, "reaction:message-1")
        self.assertEqual(saved.text, "<reaction>👍</reaction>")

    def test_whatsapp_message_marks_final_message_read(self):
        self.ingested.chat.chat_type = ChatConfigDB.ChatType.whatsapp
        self.model.responses.append(external.ai_message(content = "response"))

        self.assertTrue(self.service.process_message(self.ingested))

        self.assertEqual([message["text"] for message in self.whatsapp.get_sent_messages("123")], ["response"])
        self.assertIn("message-1", self.whatsapp.read_messages)

    def test_delayed_attempt_replies_only_after_sleep_finishes(self):
        self.addCleanup(setattr, config, "chat_burst_quiet_period_s", config.chat_burst_quiet_period_s)
        config.chat_burst_quiet_period_s = 0
        scheduled = self.service.record(self.ingested.message, is_addressed = True)
        self.model.responses.append(external.ai_message(content = "Delayed reply"))

        async def scenario():
            sleep_started = asyncio.Event()
            release_sleep = asyncio.Event()

            async def suspended_sleep(delay_s: float):
                sleep_started.set()
                await release_sleep.wait()

            # control the system timer; application processing and delivery remain real
            with patch("asyncio.sleep", new = suspended_sleep):
                task = asyncio.create_task(self.service.process_after_quiet_period(scheduled))
                try:
                    await asyncio.wait_for(sleep_started.wait(), timeout = 5)
                    self.assertFalse(task.done())
                    self.assertEqual(self.telegram.get_sent_messages("123"), [])
                finally:
                    release_sleep.set()
                    result = await asyncio.wait_for(task, timeout = 5)
                self.assertTrue(result)

        asyncio.run(scenario())
        self.assertEqual([message["text"] for message in self.telegram.get_sent_messages("123")], ["Delayed reply"])

    def test_obsolete_timer_noops_and_latest_timer_replies_once(self):
        self.addCleanup(setattr, config, "chat_burst_quiet_period_s", config.chat_burst_quiet_period_s)
        config.chat_burst_quiet_period_s = 0
        first = self.service.record(self.ingested.message, is_addressed = True)
        message = self.di.chat_message_repo.save(domain.chat_message(
            chat_id = self.ingested.chat.chat_id,
            author_id = self.ingested.author.id,
            message_id = "message-2",
            ingestion_order = None,
            sent_at = self.ingested.message.sent_at + timedelta(seconds = 1),
            text = "Another message",
        ))
        latest = self.service.record(message, is_addressed = True)
        self.model.responses.append(external.ai_message(content = "Combined reply"))

        self.assertFalse(asyncio.run(self.service.process_after_quiet_period(first)))
        self.assertEqual(self.telegram.get_sent_messages("123"), [])
        self.assertTrue(asyncio.run(self.service.process_after_quiet_period(latest)))
        self.assertFalse(asyncio.run(self.service.process_after_quiet_period(latest)))

        self.assertEqual([message["text"] for message in self.telegram.get_sent_messages("123")], ["Combined reply"])
        self.assertIn("hello", str(self.model.prompts))
        self.assertIn("Another message", str(self.model.prompts))

    def test_messages_arriving_during_processing_receive_a_followup_reply(self):
        self.addCleanup(setattr, config, "chat_burst_quiet_period_s", config.chat_burst_quiet_period_s)
        config.chat_burst_quiet_period_s = 0
        scheduled = self.service.record(self.ingested.message, is_addressed = True)

        def respond_with_another_message_waiting() -> BaseMessage:
            message = self.di.chat_message_repo.save(domain.chat_message(
                chat_id = self.ingested.chat.chat_id,
                author_id = self.ingested.author.id,
                message_id = "message-2",
                ingestion_order = None,
                sent_at = self.ingested.message.sent_at + timedelta(seconds = 1),
                text = "One more question",
            ))
            self.service.record(message, is_addressed = True)
            return external.ai_message(content = "First reply")

        self.model.responses.extend([
            respond_with_another_message_waiting,
            external.ai_message(content = "Followup reply"),
        ])

        self.assertTrue(asyncio.run(self.service.process_after_quiet_period(scheduled)))

        self.assertEqual(
            [message["text"] for message in self.telegram.get_sent_messages("123")],
            ["First reply", "Followup reply"],
        )
