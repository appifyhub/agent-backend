from datetime import datetime, timedelta
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from util.di_utils import di_for_tests

from di.di import DI
from features.currencies.exchange_rate_fetcher import CACHE_PREFIX, CACHE_TTL, ExchangeRateFetcher
from features.tools_cache.tools_cache import ToolsCache
from util.errors import ValidationError


class ExchangeRateFetcherTest(TestCase):

    di: DI
    fetcher: ExchangeRateFetcher
    http: FakeHTTPClient
    fiat_url: str = "https://currency-converter5.p.rapidapi.com/currency/convert"
    crypto_url: str = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config()))
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.fetcher = self.di.exchange_rate_fetcher
        # skip only the system delay used to space live provider requests
        self.enterContext(patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None))

    def test_execute_same_currency(self):
        result = self.fetcher.execute("USD", "USD", 100)

        self.assertEqual(result, {"from": "USD", "to": "USD", "rate": 1.0, "amount": 100, "value": 100})
        self.assertEqual(self.http.requests, [])

    def test_execute_fiat_to_fiat(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        result = self.fetcher.execute("USD", "EUR", 100)

        self.assertEqual(result, {"from": "USD", "to": "EUR", "rate": 0.85, "amount": 100, "value": 85})

    def test_execute_crypto_to_crypto(self):
        self.http.responses[self.crypto_url].extend([
            stubs.external.http_json_response(stubs.external.crypto_exchange_response(price = 31_000)),
            stubs.external.http_json_response(stubs.external.crypto_exchange_response(symbol = "ETH", price = 2_000)),
        ])

        result = self.fetcher.execute("BTC", "ETH", 1)

        self.assertEqual(result, {"from": "BTC", "to": "ETH", "rate": 15.5, "amount": 1, "value": 15.5})

    def test_execute_fiat_to_crypto(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(
            stubs.external.fiat_exchange_response(currency = "USD", rate = 1.2),
        ))
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(stubs.external.crypto_exchange_response()))

        result = self.fetcher.execute("EUR", "BTC", 1_000_000)

        self.assertEqual(result, {"from": "EUR", "to": "BTC", "rate": 1.2 * 0.000025, "amount": 1_000_000, "value": 30})

    def test_execute_force_propagates_through_every_conversion_leg(self):
        self.http.responses[self.fiat_url].extend([
            stubs.external.http_json_response(stubs.external.fiat_exchange_response(currency = "USD", rate = 1)),
            stubs.external.http_json_response(stubs.external.fiat_exchange_response(currency = "USD", rate = 1.2)),
        ])
        self.http.responses[self.crypto_url].extend([
            stubs.external.http_json_response(stubs.external.crypto_exchange_response(price = 25_000)),
            stubs.external.http_json_response(stubs.external.crypto_exchange_response()),
        ])
        self.assertEqual(self.fetcher.execute("EUR", "BTC")["rate"], 1 / 25_000)

        result = self.fetcher.execute("EUR", "BTC", force = True)

        self.assertAlmostEqual(result["rate"], 0.00003)
        self.assertEqual([url for url, _ in self.http.requests], [self.fiat_url, self.crypto_url] * 2)

    def test_execute_unsupported_currency(self):
        with self.assertRaises(ValidationError):
            self.fetcher.execute("USD", "UNSUPPORTED", 100)

        self.assertEqual(self.http.requests, [])

    def test_get_crypto_conversion_rate_cache_hit(self):
        self.di.tools_cache_repo.save(stubs.domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, "BTC-ETH"),
            value = "1.5",
            expires_at = datetime.now() + CACHE_TTL,
        ))

        rate = self.fetcher.get_crypto_conversion_rate("BTC", "ETH")

        self.assertEqual(rate, 1.5)
        self.assertEqual(self.http.requests, [])

    def test_get_crypto_conversion_rate_force_bypasses_cache(self):
        self.http.responses[self.crypto_url].extend([
            stubs.external.http_json_response(stubs.external.crypto_exchange_response(price = 25_000)),
            stubs.external.http_json_response(stubs.external.crypto_exchange_response()),
        ])
        self.assertEqual(self.fetcher.get_crypto_conversion_rate("BTC", "USD"), 25_000)

        rate = self.fetcher.get_crypto_conversion_rate("BTC", "USD", force = True)

        self.assertEqual(rate, 40_000)
        self.assertEqual(len(self.http.requests), 2)
        self.assertEqual(self.fetcher.get_crypto_conversion_rate("BTC", "USD"), rate)
        self.assertEqual(len(self.http.requests), 2)

    def test_get_crypto_conversion_rate_inverse_cache_hit(self):
        self.di.tools_cache_repo.save(stubs.domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, "ETH-BTC"),
            value = "1.5",
            expires_at = datetime.now() + CACHE_TTL,
        ))

        rate = self.fetcher.get_crypto_conversion_rate("BTC", "ETH")

        self.assertEqual(rate, 1 / 1.5)
        self.assertEqual(self.http.requests, [])

    def test_get_crypto_conversion_rate_cache_miss_crypto_to_crypto(self):
        self.http.responses[self.crypto_url].extend([
            stubs.external.http_json_response(stubs.external.crypto_exchange_response()),
            stubs.external.http_json_response(stubs.external.crypto_exchange_response(symbol = "ETH", price = 2_000)),
        ])
        before = datetime.now()

        rate = self.fetcher.get_crypto_conversion_rate("BTC", "ETH")

        self.assertEqual(rate, 20)
        saved_entry = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, "BTC-ETH"))
        self.assertEqual(saved_entry.value, "20.0")
        self.assertFalse(saved_entry.is_expired())
        self.assertGreaterEqual(saved_entry.expires_at, before + CACHE_TTL)
        self.assertLessEqual(saved_entry.expires_at, datetime.now() + CACHE_TTL)
        self.assertEqual([options["params"]["symbol"] for _, options in self.http.requests], ["BTC", "ETH"])

    def test_get_crypto_conversion_rate_cache_miss_crypto_to_usd(self):
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(stubs.external.crypto_exchange_response()))

        rate = self.fetcher.get_crypto_conversion_rate("BTC", "USD")

        self.assertEqual(rate, 40_000)
        self.assertEqual(self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, "BTC-USD")).value, "40000.0")

    def test_get_fiat_conversion_rate_cache_hit(self):
        self.di.tools_cache_repo.save(stubs.domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, "USD-EUR"),
            value = "1.5",
            expires_at = datetime.now() + CACHE_TTL,
        ))

        rate = self.fetcher.get_fiat_conversion_rate("USD", "EUR")

        self.assertEqual(rate, 1.5)
        self.assertEqual(self.http.requests, [])

    def test_get_fiat_conversion_rate_force_bypasses_cache(self):
        self.http.responses[self.fiat_url].extend([
            stubs.external.http_json_response(stubs.external.fiat_exchange_response(rate = 0.7)),
            stubs.external.http_json_response(stubs.external.fiat_exchange_response()),
        ])
        self.assertEqual(self.fetcher.get_fiat_conversion_rate("USD", "EUR"), 0.7)

        rate = self.fetcher.get_fiat_conversion_rate("USD", "EUR", force = True)

        self.assertEqual(rate, 0.85)
        self.assertEqual(len(self.http.requests), 2)
        self.assertEqual(self.fetcher.get_fiat_conversion_rate("USD", "EUR"), rate)
        self.assertEqual(len(self.http.requests), 2)

    def test_get_fiat_conversion_rate_expired_cache_miss(self):
        key = ToolsCache.create_key(CACHE_PREFIX, "USD-EUR")
        self.di.tools_cache_repo.save(stubs.domain.tools_cache(
            key = key, value = "0.7", expires_at = datetime.now() - timedelta(seconds = 1),
        ))
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        rate = self.fetcher.get_fiat_conversion_rate("USD", "EUR")

        self.assertEqual(rate, 0.85)
        entry = self.di.tools_cache_repo.get(key)
        self.assertEqual(entry.value, "0.85")
        self.assertFalse(entry.is_expired())

    def test_get_fiat_conversion_rate_cache_miss(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        rate = self.fetcher.get_fiat_conversion_rate("USD", "EUR")

        self.assertEqual(rate, 0.85)
        self.assertEqual(self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, "USD-EUR")).value, "0.85")
