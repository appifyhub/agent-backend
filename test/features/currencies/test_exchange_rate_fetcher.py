import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import requests_mock
from pydantic import SecretStr
from requests_mock.mocker import Mocker

from db.crud.tools_cache import ToolsCacheCRUD
from db.crud.user import UserCRUD
from db.model.user import UserDB
from db.schema.tools_cache import ToolsCache
from db.schema.user import User
from di.di import DI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.currencies.exchange_rate_fetcher import CACHE_TTL, ExchangeRateFetcher
from features.web_browsing.web_fetcher import WebFetcher
from util.config import config
from util.errors import ValidationError


class ExchangeRateFetcherTest(unittest.TestCase):

    cached_rate: str
    user: User
    cache_entry: ToolsCache
    mock_user_crud: UserCRUD
    mock_cache_crud: ToolsCacheCRUD
    mock_telegram_sdk: TelegramBotSDK

    def setUp(self):
        config.web_timeout_s = 1
        self.cached_rate = "1.5"
        self.cache_entry = ToolsCache(
            key = "test_cache_key",
            value = self.cached_rate,
            expires_at = datetime.now() + CACHE_TTL,
        )
        self.user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_api_key"),
            rapid_api_key = SecretStr("test_rapid_api_key"),
            coinmarketcap_key = SecretStr("test_coinmarketcap_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        # Create a DI mock and set required properties
        self.mock_di = MagicMock(spec = DI)
        self.mock_di.invoker = self.user

        # Mock chat for usage tracking
        mock_chat = MagicMock()
        mock_chat.chat_id = UUID(int = 2)
        self.mock_di.require_invoker_chat = MagicMock(return_value = mock_chat)

        self.mock_di.tools_cache_crud = MagicMock(spec = ToolsCacheCRUD)
        self.mock_di.access_token_resolver = MagicMock()

        # Mock web_fetcher to return a mock WebFetcher instance
        self.mock_web_fetcher = MagicMock(spec = WebFetcher)
        self.mock_di.web_fetcher.return_value = self.mock_web_fetcher

        # Mock tracked_web_fetcher to return the same mock WebFetcher instance
        self.mock_di.tracked_web_fetcher.return_value = self.mock_web_fetcher

        # Mock access token resolver
        self.mock_di.access_token_resolver.require_access_token_for_tool.return_value.get_secret_value.return_value = "test_token"

        # Set up the cache CRUD mock
        self.mock_di.tools_cache_crud.create_key.return_value = "test_cache_key"
        self.mock_di.tools_cache_crud.get.return_value = None
        self.mock_sponsorship_dao = MagicMock()
        self.mock_sponsorship_dao.get_all_by_receiver.return_value = []
        self.mock_telegram_sdk = MagicMock()

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @requests_mock.Mocker()
    def test_execute_same_currency(self, m: Mocker, mock_sleep):
        fetcher = ExchangeRateFetcher(self.mock_di)
        result = fetcher.execute("USD", "USD", 100)
        self.assertEqual(result, {"from": "USD", "to": "USD", "rate": 1.0, "amount": 100, "value": 100})

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @patch("features.currencies.exchange_rate_fetcher.ExchangeRateFetcher.get_fiat_conversion_rate")
    def test_execute_fiat_to_fiat(self, mock_get_fiat, mock_sleep):
        mock_get_fiat.return_value = 0.85
        fetcher = ExchangeRateFetcher(self.mock_di)
        result = fetcher.execute("USD", "EUR", 100)
        self.assertEqual(result, {"from": "USD", "to": "EUR", "rate": 0.85, "amount": 100, "value": 85})

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @patch("features.currencies.exchange_rate_fetcher.ExchangeRateFetcher.get_crypto_conversion_rate")
    def test_execute_crypto_to_crypto(self, mock_get_crypto, mock_sleep):
        mock_get_crypto.return_value = 15.5
        fetcher = ExchangeRateFetcher(self.mock_di)
        result = fetcher.execute("BTC", "ETH", 1)
        self.assertEqual(result, {"from": "BTC", "to": "ETH", "rate": 15.5, "amount": 1, "value": 15.5})

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @patch("features.currencies.exchange_rate_fetcher.ExchangeRateFetcher.get_fiat_conversion_rate")
    @patch("features.currencies.exchange_rate_fetcher.ExchangeRateFetcher.get_crypto_conversion_rate")
    def test_execute_fiat_to_crypto(self, mock_get_crypto, mock_get_fiat, mock_sleep):
        mock_get_fiat.return_value = 1.2  # EUR to USD
        mock_get_crypto.return_value = 0.000025  # USD to BTC (1 BTC = 40,000 USD)
        fetcher = ExchangeRateFetcher(self.mock_di)
        result = fetcher.execute("EUR", "BTC", 1000000)  # 1 million EUR
        expected_rate = 1.2 * 0.000025
        expected_result = {"from": "EUR", "to": "BTC", "rate": expected_rate, "amount": 1000000, "value": 30}
        self.assertEqual(result, expected_result)

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    def test_execute_unsupported_currency(self, mock_sleep):
        fetcher = ExchangeRateFetcher(self.mock_di)
        with self.assertRaises(ValidationError):
            fetcher.execute("USD", "UNSUPPORTED", 100)

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @requests_mock.Mocker()
    def test_get_crypto_conversion_rate_cache_hit(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_crud.get.return_value = self.cache_entry
        fetcher = ExchangeRateFetcher(self.mock_di)
        rate = fetcher.get_crypto_conversion_rate("BTC", "ETH")
        self.assertEqual(rate, 1.5)
        # noinspection PyUnresolvedReferences
        m.assert_not_called()

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    def test_get_crypto_conversion_rate_cache_miss_crypto_to_crypto(self, mock_sleep):
        self.mock_di.tools_cache_crud.get.return_value = None
        self.mock_web_fetcher.fetch_json.side_effect = [
            {"data": {"BTC": {"quote": {"USD": {"price": 40000}}}}},
            {"data": {"ETH": {"quote": {"USD": {"price": 2000}}}}},
        ]
        fetcher = ExchangeRateFetcher(self.mock_di)
        rate = fetcher.get_crypto_conversion_rate("BTC", "ETH")
        self.assertEqual(rate, 20)  # 40000 / 2000 = 20
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_crud.save.assert_called_once()

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    def test_get_crypto_conversion_rate_cache_miss_crypto_to_usd(self, mock_sleep):
        self.mock_di.tools_cache_crud.get.return_value = None
        self.mock_web_fetcher.fetch_json.return_value = {"data": {"BTC": {"quote": {"USD": {"price": 40000}}}}}
        fetcher = ExchangeRateFetcher(self.mock_di)
        rate = fetcher.get_crypto_conversion_rate("BTC", "USD")
        self.assertEqual(rate, 40000)
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_crud.save.assert_called_once()

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    @requests_mock.Mocker()
    def test_get_fiat_conversion_rate_cache_hit(self, m: Mocker, mock_sleep):
        self.mock_di.tools_cache_crud.get.return_value = self.cache_entry
        fetcher = ExchangeRateFetcher(self.mock_di)
        rate = fetcher.get_fiat_conversion_rate("USD", "EUR")
        self.assertEqual(rate, 1.5)
        # noinspection PyUnresolvedReferences
        m.assert_not_called()

    # noinspection PyUnusedLocal
    @patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None)
    def test_get_fiat_conversion_rate_cache_miss(self, mock_sleep):
        self.mock_di.tools_cache_crud.get.return_value = None
        self.mock_web_fetcher.fetch_json.return_value = {"rates": {"EUR": {"rate_for_amount": "0.85"}}}
        fetcher = ExchangeRateFetcher(self.mock_di)
        rate = fetcher.get_fiat_conversion_rate("USD", "EUR")
        self.assertEqual(rate, 0.85)
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_crud.save.assert_called_once()
