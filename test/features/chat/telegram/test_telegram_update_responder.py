import asyncio
from datetime import datetime
from typing import cast
from unittest import TestCase

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.telegram.telegram_update_responder import _ingest_update, respond_to_update
from features.integrations.integrations import resolve_agent_user, resolve_external_handle
from util.config import config


class TelegramUpdateResponderTest(TestCase):

    di: DI
    api: FakeTelegramBotAPI
    model: FakeChatModel

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.user_repo.save(domain.user())
        self.di.chat_config_repo.save(domain.chat_config(external_id = "123456789"))
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(domain.configured_tool(), max_tokens = 500))
        self.addCleanup(setattr, config, "chat_burst_quiet_period_s", config.chat_burst_quiet_period_s)
        config.chat_burst_quiet_period_s = 0

    def test_command_is_processed_without_creating_burst(self):
        chat_type = ChatConfigDB.ChatType.telegram
        handle = resolve_external_handle(resolve_agent_user(chat_type), chat_type)
        update = external.telegram_update(message = external.telegram_message(
            text = f"/help@{handle}",
            date = int(datetime.now().timestamp()),
            **{"from": external.telegram_user()},
        ))

        outcome = _ingest_update(update)

        self.assertIsNone(outcome.scheduled_burst)
        self.assertEqual(len(self.api.get_sent_messages("123456789")), 1)
        self.assertEqual(self.api.get_sent_messages("123456789")[0]["link_url"], "https://example.com/short")
        self.assertEqual(self.model.prompts, [])

    def test_async_responder_delivers_reply(self):
        self.model.responses.append(external.ai_message(content = "Hello back"))
        update = external.telegram_update(message = external.telegram_message(
            text = "Hello",
            date = int(datetime.now().timestamp()),
            **{"from": external.telegram_user()},
        ))

        result = asyncio.run(respond_to_update(update))

        self.assertTrue(result)
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("123456789")], ["Hello back"])
