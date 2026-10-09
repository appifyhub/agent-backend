from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.config.chat_config import ChatConfig, ChatConfigDB
from features.currencies.asset_alert_responder import respond_with_asset_alerts
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from util.error_codes import UNEXPECTED_ERROR
from util.errors import ExternalServiceError


class AssetAlertResponderTest(TestCase):

    di: DI
    chat: ChatConfig
    tool: ConfiguredTool
    model: FakeChatModel
    http: FakeHTTPClient
    bot: FakeTelegramBotAPI
    crypto_url: str = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.chat = self.di.chat_config_repo.save(stubs.domain.chat_config())
        self.di.inject_invoker_chat(self.chat)
        self.tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool))
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        # skip the system delay between provider requests
        self.enterContext(patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None))

    def test_sys_announcements_service_normalizes_structured_content(self):
        self.model.responses.append(stubs.external.ai_message(content = [
            {"type": "thinking", "thinking": "Hidden reasoning"},
            {"type": "text", "text": "System announcement"},
        ]))
        service = self.di.sys_announcements_service("Raw information", self.chat, self.tool)

        resolved_chat, response = service.execute()

        self.assertEqual(resolved_chat, self.chat)
        self.assertEqual(response.content, "System announcement")

    def test_sys_announcement_generation_does_not_require_delivery_credits(self):
        user = self.di.user_repo.save(replace(
            self.di.invoker,
            credit_balance = 0.0,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(replace(
            self.chat,
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = user.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(
            chat_id = chat.chat_id,
            user_id = user.id,
        ))
        self.di.inject_invoker(user)
        self.di.inject_invoker_chat(chat)
        tool = replace(self.tool, payer_id = user.id, uses_credits = False)
        self.model.responses.append(stubs.external.ai_message(content = "System announcement"))

        _, response = self.di.sys_announcements_service("Raw information", chat, tool).execute()

        self.assertEqual(response.content, "System announcement")
        self.assertEqual(len(self.model.prompts), 1)

    def test_successful_announcements(self):
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        self.di.price_alert_repo.save(stubs.domain.price_alert())
        self.di.price_alert_repo.save(stubs.domain.price_alert(chat_id = other_chat.chat_id, threshold_percent = 10))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))
        self.model.responses.extend([
            stubs.external.ai_message(content = "Bitcoin price increased"),
            stubs.external.ai_message(content = "Bitcoin price increased"),
        ])

        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 2, "announcements_created": 2, "chats_affected": 2, "chats_notified": 2,
        })
        for chat in (self.chat, other_chat):
            self.assertEqual([message["text"] for message in self.bot.get_sent_messages(chat.external_id)], ["Bitcoin price increased"])  # ruff: ignore[line-too-long]
        self.assertEqual(len(self.model.prompts), 2)

    def test_no_triggered_alerts(self):
        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 0, "announcements_created": 0, "chats_affected": 0, "chats_notified": 0,
        })
        self.assertEqual(self.bot.get_sent_messages(self.chat.external_id), [])
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.http.requests, [])

    def test_announcement_creation_failure(self):

        self.di.price_alert_repo.save(stubs.domain.price_alert())
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))
        self.model.responses.append(stubs.external.ai_message(content = ""))

        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 1, "announcements_created": 0, "chats_affected": 1, "chats_notified": 0,
        })
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.bot.get_sent_messages(self.chat.external_id), [])

    def test_uncached_announcement_blocks_unfunded_whatsapp_before_model(self):
        user = self.di.user_repo.save(replace(
            self.di.invoker,
            credit_balance = 0.0,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(replace(
            self.chat,
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = user.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(
            chat_id = chat.chat_id,
            user_id = user.id,
        ))
        self.di.price_alert_repo.save(stubs.domain.price_alert(
            owner_id = user.id,
            chat_id = chat.chat_id,
        ))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))

        with patch("features.currencies.asset_alert_responder.log.w") as warning_log:
            result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 1, "announcements_created": 0, "chats_affected": 1, "chats_notified": 0,
        })
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.bot.get_sent_messages(str(chat.external_id)), [])
        warning_log.assert_called_once_with(f"Skipping price alert for chat #{chat.chat_id} due to insufficient delivery credits")  # ruff: ignore[line-too-long]

    def test_notification_failure(self):
        self.di.price_alert_repo.save(stubs.domain.price_alert())
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))
        self.model.responses.append(stubs.external.ai_message(content = "Bitcoin price increased"))
        self.bot.delivery_errors[self.chat.external_id] = ExternalServiceError("Notification failed", UNEXPECTED_ERROR)

        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 1, "announcements_created": 1, "chats_affected": 1, "chats_notified": 0,
        })
        self.assertEqual(self.bot.get_sent_messages(self.chat.external_id), [])

    def test_cached_announcement(self):
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        self.di.price_alert_repo.save(stubs.domain.price_alert())
        self.di.price_alert_repo.save(stubs.domain.price_alert(chat_id = other_chat.chat_id))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))
        self.model.responses.append(stubs.external.ai_message(content = "Shared announcement"))

        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 2, "announcements_created": 1, "chats_affected": 2, "chats_notified": 2,
        })
        self.assertEqual(len(self.model.prompts), 1)
        for chat in (self.chat, other_chat):
            self.assertEqual([message["text"] for message in self.bot.get_sent_messages(chat.external_id)], ["Shared announcement"])  # ruff: ignore[line-too-long]

    def test_cached_announcement_blocks_unfunded_whatsapp_before_send(self):
        other_owner = self.di.user_repo.save(stubs.domain.user(
            id = uuid4(),
            credit_balance = 0.0,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "15551234567",
            whatsapp_phone_number = "+15551234568",
            connect_key = "ASST-ALRT-0001",
        ))
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = other_owner.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(
            chat_id = other_chat.chat_id,
            user_id = other_owner.id,
        ))
        self.di.price_alert_repo.save(stubs.domain.price_alert(
            owner_id = self.di.invoker.id,
            chat_id = self.chat.chat_id,
        ))
        self.di.price_alert_repo.save(stubs.domain.price_alert(
            owner_id = other_owner.id,
            chat_id = other_chat.chat_id,
        ))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 55_000),
        ))
        self.model.responses.append(stubs.external.ai_message(content = "Shared announcement"))

        result = respond_with_asset_alerts(self.di)

        self.assertEqual(result, {
            "alerts_triggered": 2, "announcements_created": 1, "chats_affected": 2, "chats_notified": 1,
        })
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual([message["text"] for message in self.bot.get_sent_messages(self.chat.external_id)], ["Shared announcement"])  # ruff: ignore[line-too-long]
