from dataclasses import replace
from datetime import datetime
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import stubs
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from pydantic import SecretStr
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.currencies.asset_alert_service import DATETIME_PRINT_FORMAT, AssetAlertService
from features.currencies.asset_price import AssetType
from features.currencies.price_alert_repo import PriceAlertRepository
from features.users.user import User
from util.error_codes import NOT_CHAT_ADMIN, STOCK_QUOTE_FAILED
from util.errors import AuthorizationError, ExternalServiceError


class AssetAlertServiceTest(TestCase):

    di: DI
    user: User
    chat: ChatConfig
    service: AssetAlertService
    repo: PriceAlertRepository
    http: FakeHTTPClient
    bot: FakeTelegramBotAPI
    crypto_url: str = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    stock_url: str = "https://api.twelvedata.com/quote"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.di.inject_invoker(self.user)
        self.di.inject_invoker_chat(self.chat)
        self.service = self.di.asset_alert_service(self.chat.chat_id.hex)
        self.repo = self.di.price_alert_repo
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()
        # skip the system delay between provider requests
        self.enterContext(patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None))

    def test_create_alert(self):
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1.5),
        ))

        alert = self.service.create_alert("BTC", "USD", 5)

        self.assertEqual(alert.chat_id, self.chat.chat_id)
        self.assertEqual(alert.owner_id, self.user.id)
        self.assertEqual(alert.asset_id, "BTC")
        self.assertEqual(alert.currency, "USD")
        self.assertEqual(alert.threshold_percent, 5)
        self.assertEqual(alert.last_price, 1.5)
        saved = self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.chat_id, self.chat.chat_id)
        self.assertEqual(saved.owner_id, self.user.id)
        self.assertEqual(saved.asset_type, AssetType.crypto)
        self.assertEqual(saved.asset_id, "BTC")
        self.assertEqual(saved.currency, "USD")
        self.assertEqual(saved.threshold_percent, 5)
        self.assertEqual(saved.last_price, 1.5)

    def test_create_stock_alert_persists_exchange_qualified_identity(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_response()))

        alert = self.service.create_alert("AAPL", "USD", 5, "stock")

        self.assertEqual(alert.asset_type, AssetType.stock)
        self.assertEqual(alert.asset_id, "XNAS:AAPL")
        self.assertEqual(alert.last_price, 210.5)
        saved = self.repo.get(self.chat.chat_id, AssetType.stock, "XNAS:AAPL", "USD")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.asset_type, AssetType.stock)
        self.assertEqual(saved.asset_id, "XNAS:AAPL")
        self.assertEqual(saved.last_price, 210.5)

    def test_admin_can_create_alert(self):
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1.5),
        ))

        alert = self.service.create_alert("BTC", "USD", 5)

        stored = self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(alert.owner_id, self.user.id)
        self.assertEqual(stored.owner_id, self.user.id)
        self.assertEqual(stored.threshold_percent, 5)
        self.assertEqual(stored.last_price, 1.5)

    def test_admin_can_reconfigure_alert(self):
        self.repo.save(stubs.domain.price_alert(last_price = 1.5, last_price_time = datetime(2023, 1, 1, 12)))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 2.5),
        ))

        alert = self.service.create_alert("BTC", "USD", 8)

        stored = self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(alert.threshold_percent, 8)
        self.assertEqual(stored.owner_id, self.user.id)
        self.assertEqual(stored.threshold_percent, 8)
        self.assertEqual(stored.last_price, 2.5)

    def test_private_chat_owner_can_create_alert(self):
        chat = self.di.chat_config_repo.save(replace(self.chat, is_private = True, external_id = self.user.telegram_chat_id))
        self.di.inject_invoker_chat(chat)
        service = self.di.asset_alert_service(chat.chat_id.hex)
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1.5),
        ))

        service.create_alert("BTC", "USD", 5)

        stored = self.repo.get(chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.owner_id, self.user.id)
        self.assertEqual(stored.threshold_percent, 5)

    def test_get_all_alerts(self):
        self.repo.save(stubs.domain.price_alert())
        self.repo.save(stubs.domain.price_alert(asset_id = "ETH"))
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        self.repo.save(stubs.domain.price_alert(chat_id = other_chat.chat_id))

        alerts = self.service.get_active_alerts()

        self.assertEqual(len(alerts), 2)
        self.assertEqual({alert.asset_id for alert in alerts}, {"BTC", "ETH"})
        self.assertTrue(all(alert.chat_id == self.chat.chat_id for alert in alerts))

    def test_get_all_alerts_without_target_chat(self):
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        self.repo.save(stubs.domain.price_alert())
        self.repo.save(stubs.domain.price_alert(chat_id = other_chat.chat_id))
        service = self.di.asset_alert_service(None)

        alerts = service.get_active_alerts()

        self.assertEqual(len(alerts), 2)
        self.assertEqual({alert.chat_id for alert in alerts}, {self.chat.chat_id, other_chat.chat_id})

    def test_delete_alert(self):
        self.repo.save(stubs.domain.price_alert())

        deleted_alert = self.service.delete_alert("BTC", "USD")

        self.assertIsNotNone(deleted_alert)
        self.assertEqual(deleted_alert.asset_id, "BTC")
        self.assertEqual(deleted_alert.currency, "USD")
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_admin_can_delete_alert(self):
        self.repo.save(stubs.domain.price_alert())

        deleted_alert = self.service.delete_alert("BTC", "USD")

        self.assertIsNotNone(deleted_alert)
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_delete_normalized_stock_identity_does_not_fetch_quote(self):
        self.repo.save(stubs.domain.price_alert(asset_type = AssetType.stock, asset_id = "XNAS:AAPL"))

        deleted = self.service.delete_alert(" xnas:aapl ", " usd ", "stock")

        self.assertIsNotNone(deleted)
        self.assertEqual(deleted.asset_type, AssetType.stock)
        self.assertEqual(deleted.asset_id, "XNAS:AAPL")
        self.assertEqual(deleted.currency, "USD")
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.stock, "XNAS:AAPL", "USD"))
        self.assertEqual(self.http.requests, [])

    def test_delete_unresolved_stock_forwards_provider_error(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(
            stubs.external.stock_quote_error_response(message = "Specify an exchange"),
        ))

        with self.assertRaises(ExternalServiceError) as context:
            self.service.delete_alert("DHER", "EUR", "stock")

        self.assertEqual(context.exception.error_code, STOCK_QUOTE_FAILED)

    def test_member_cannot_create_alert(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()

        with self.assertRaises(AuthorizationError) as context:
            self.service.create_alert("BTC", "USD", 5)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        self.assertEqual(self.http.requests, [])
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_member_cannot_reconfigure_alert(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()
        original = self.repo.save(stubs.domain.price_alert(last_price = 1.5, last_price_time = datetime(2023, 1, 1, 12)))

        with self.assertRaises(AuthorizationError) as context:
            self.service.create_alert("BTC", "USD", 8)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"), original)

    def test_member_cannot_delete_alert(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()
        original = self.repo.save(stubs.domain.price_alert())

        with self.assertRaises(AuthorizationError) as context:
            self.service.delete_alert("BTC", "USD")

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        self.assertEqual(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"), original)

    def test_lost_admin_role_cannot_create_alert(self):
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(is_admin = True))
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()

        with self.assertRaises(AuthorizationError) as context:
            self.service.create_alert("BTC", "USD", 5)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        self.assertEqual(self.http.requests, [])
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_non_participant_cannot_create_alert(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member_left()

        with self.assertRaises(AuthorizationError):
            self.service.create_alert("BTC", "USD", 5)

        self.assertEqual(self.http.requests, [])
        self.assertIsNone(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_listing_does_not_require_admin_role(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()
        self.repo.save(stubs.domain.price_alert())

        alerts = self.service.get_active_alerts()

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].asset_id, "BTC")

    def test_triggered_alert_refreshes_only_price_state(self):
        existing = self.repo.save(stubs.domain.price_alert(last_price = 1000, last_price_time = datetime(2023, 1, 1, 12)))
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1100),
        ))

        triggered_alerts = self.service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(triggered_alerts[0].currency, "USD")
        self.assertEqual(triggered_alerts[0].old_price, 1000)
        self.assertEqual(triggered_alerts[0].new_price, 1100)
        self.assertEqual(triggered_alerts[0].price_change_percent, 10)
        self.assertEqual(triggered_alerts[0].old_price_time, existing.last_price_time.strftime(DATETIME_PRINT_FORMAT))
        refreshed = self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed, replace(existing, last_price = 1100, last_price_time = refreshed.last_price_time))
        self.assertGreater(refreshed.last_price_time, existing.last_price_time)

    def test_triggered_alert_with_zero_last_price(self):
        self.repo.save(stubs.domain.price_alert(last_price = 0))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1000),
        ))

        triggered_alerts = self.service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(triggered_alerts[0].currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 100000)

    def test_alert_below_threshold_is_not_triggered(self):
        original = self.repo.save(stubs.domain.price_alert(last_price = 1000))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 1020),
        ))

        triggered_alerts = self.service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.assertEqual(self.repo.get(self.chat.chat_id, AssetType.crypto, "BTC", "USD"), original)

    def test_equivalent_owner_alerts_across_chats_share_a_quote(self):
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        for chat in (self.chat, other_chat):
            self.repo.save(stubs.domain.price_alert(
                chat_id = chat.chat_id, asset_type = AssetType.stock, asset_id = "XNAS:AAPL", last_price = 100,
            ))
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(
            stubs.external.stock_quote_response(close = "110"),
        ))
        service = self.di.asset_alert_service(None)

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual({alert.chat_id for alert in triggered_alerts}, {self.chat.chat_id, other_chat.chat_id})
        self.assertEqual([alert.new_price for alert in triggered_alerts], [110, 110])
        self.assertEqual([url for url, _ in self.http.requests], [self.stock_url])

    def test_same_lookup_for_different_owners_uses_each_owner_scope(self):
        other_user = self.di.user_repo.save(stubs.domain.user(
            id = uuid4(), telegram_user_id = None, whatsapp_user_id = None, connect_key = "OTHER-OWNER",
            twelve_data_api_key = SecretStr("other-owner-key"),
        ))
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        for user, chat in ((self.user, self.chat), (other_user, other_chat)):
            self.repo.save(stubs.domain.price_alert(
                chat_id = chat.chat_id, owner_id = user.id,
                asset_type = AssetType.stock, asset_id = "XNAS:AAPL", last_price = 100,
            ))
            self.http.responses[self.stock_url].append(stubs.external.http_json_response(
                stubs.external.stock_quote_response(close = "102"),
            ))
        service = self.di.asset_alert_service(None)

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.assertCountEqual(
            [kwargs["headers"]["Authorization"] for _, kwargs in self.http.requests],
            ["apikey test-twelve-data-key", "apikey other-owner-key"],
        )

    def test_price_fetch_failure_skips_alert(self):
        original = self.repo.save(stubs.domain.price_alert(asset_type = AssetType.stock, asset_id = "XNAS:AAPL"))
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_error_response()))

        triggered_alerts = self.service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.assertEqual(self.repo.get(self.chat.chat_id, AssetType.stock, "XNAS:AAPL", "USD"), original)
        self.assertEqual([url for url, _ in self.http.requests], [self.stock_url])

    def test_failed_shared_quote_leaves_alerts_unchanged_and_distinct_alert_continues(self):
        other_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "other-chat"))
        failed_alerts = [
            self.repo.save(stubs.domain.price_alert(
                chat_id = chat.chat_id, asset_type = AssetType.stock, asset_id = "XNAS:AAPL", last_price = 100,
            ))
            for chat in (self.chat, other_chat)
        ]
        self.repo.save(stubs.domain.price_alert(last_price = 100))
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_error_response()))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 110),
        ))
        service = self.di.asset_alert_service(None)

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(triggered_alerts[0].new_price, 110)
        self.assertCountEqual([url for url, _ in self.http.requests], [self.stock_url, self.crypto_url])
        for alert in failed_alerts:
            self.assertEqual(self.repo.get(alert.chat_id, alert.asset_type, alert.asset_id, alert.currency), alert)
