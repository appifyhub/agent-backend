from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from util.di_utils import di_for_tests

from di.di import DI
from features.currencies.asset_price import AssetType
from features.currencies.asset_price_service import AssetPriceService
from util.error_codes import INVALID_ASSET_AMOUNT, INVALID_ASSET_TYPE, INVALID_CURRENCY
from util.errors import ValidationError


class AssetPriceServiceTest(TestCase):

    di: DI
    service: AssetPriceService
    http: FakeHTTPClient
    fiat_url: str = "https://currency-converter5.p.rapidapi.com/currency/convert"
    crypto_url: str = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    stock_url: str = "https://api.twelvedata.com/quote"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config()))
        self.service = self.di.asset_price_service
        self.http = cast(FakeHTTPClient, self.di.http_client())
        # keep the real fetchers; skip the system delay between provider requests
        self.enterContext(patch("features.currencies.exchange_rate_fetcher.sleep", return_value = None))

    def test_fiat_inference_normalizes_markers_and_preserves_amount(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        result = self.service.execute(" usd ", " eur ", amount = 250)

        self.assertEqual(result.asset, "USD")
        self.assertEqual(result.asset_type, AssetType.fiat)
        self.assertEqual(result.amount, 250)
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.unit_price, 0.85)
        self.assertEqual(result.value, 212.5)
        self.assertEqual([url for url, _ in self.http.requests], [self.fiat_url])
        self.assertEqual(self.http.requests[0][1]["params"], {"format": "json", "from": "USD", "to": "EUR", "amount": "1.0"})

    def test_crypto_inference_routes_to_exchange_rate_fetcher(self):
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(price = 100_000),
        ))

        result = self.service.execute("btc", "usd", amount = 2, force = True)

        self.assertEqual(result.asset_type, AssetType.crypto)
        self.assertEqual(result.unit_price, 100_000)
        self.assertEqual(result.value, 200_000)
        self.assertEqual([url for url, _ in self.http.requests], [self.crypto_url])

    def test_omitted_type_uses_crypto_for_aapl_collision(self):
        self.http.responses[self.crypto_url].append(stubs.external.http_json_response(
            stubs.external.crypto_exchange_response(symbol = "AAPL", price = 0.01),
        ))

        result = self.service.execute("AAPL", "USD")

        self.assertEqual(result.asset_type, AssetType.crypto)
        self.assertEqual(result.unit_price, 0.01)
        self.assertEqual([url for url, _ in self.http.requests], [self.crypto_url])

    def test_explicit_stock_overrides_aapl_collision(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_response()))

        result = self.service.execute(" aapl ", " usd ", asset_type = " STOCK ")

        self.assertEqual(result.asset_type, AssetType.stock)
        self.assertEqual(result.asset, "XNAS:AAPL")
        self.assertEqual([url for url, _ in self.http.requests], [self.stock_url])
        self.assertEqual(self.http.requests[0][1]["params"], {"symbol": "AAPL"})

    def test_unknown_marker_is_inferred_as_stock(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(
            stubs.external.stock_quote_response(symbol = "BRK.B", exchange = "NYSE", mic_code = None, close = "500"),
        ))

        result = self.service.execute("brk.b", "usd")

        self.assertEqual(result.asset_type, AssetType.stock)
        self.assertEqual(result.asset, "NYSE:BRK.B")
        self.assertEqual(result.unit_price, 500)

    def test_native_stock_price_preserves_metadata_and_calculates_amount(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_response()))

        result = self.service.execute("AAPL", "USD", asset_type = "stock", amount = 3)

        self.assertEqual(result.asset, "XNAS:AAPL")
        self.assertEqual(result.unit_price, 210.5)
        self.assertEqual(result.value, 631.5)
        self.assertEqual(result.native_price, 210.5)
        self.assertEqual(result.native_currency, "USD")
        self.assertEqual(result.provider, "twelve-data")
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.exchange, "NASDAQ")
        self.assertEqual(result.mic_code, "XNAS")
        self.assertEqual(result.timestamp, 1_753_352_400)
        self.assertTrue(result.is_market_open)
        self.assertEqual([url for url, _ in self.http.requests], [self.stock_url])
        serialized = result.as_dict()
        self.assertNotIn("timestamp", serialized)
        self.assertEqual(serialized["datetime"], "2025-07-24T10:20:00+00:00")

    def test_stock_price_converts_from_native_currency_and_propagates_force(self):
        self.http.responses[self.stock_url].extend([
            stubs.external.http_json_response(stubs.external.stock_quote_response(close = "200")),
            stubs.external.http_json_response(stubs.external.stock_quote_response()),
        ])
        self.http.responses[self.fiat_url].extend([
            stubs.external.http_json_response(stubs.external.fiat_exchange_response(rate = 0.5)),
            stubs.external.http_json_response(stubs.external.fiat_exchange_response(rate = 0.8)),
        ])
        self.assertEqual(self.service.execute("AAPL", "EUR", asset_type = "stock").value, 100)

        result = self.service.execute("AAPL", "EUR", asset_type = "stock", amount = 2, force = True)

        self.assertEqual(result.unit_price, 168.4)
        self.assertEqual(result.value, 336.8)
        self.assertEqual(result.native_price, 210.5)
        self.assertEqual([url for url, _ in self.http.requests], [self.stock_url, self.fiat_url] * 2)

    def test_normalized_stock_identity_is_converted_to_provider_qualifier_order(self):
        self.http.responses[self.stock_url].append(stubs.external.http_json_response(stubs.external.stock_quote_response()))

        result = self.service.execute_normalized(asset_id = "XNAS:AAPL", currency = "USD", asset_type = AssetType.stock)

        self.assertEqual(result.asset, "XNAS:AAPL")
        self.assertEqual(self.http.requests[0][1]["params"], {"symbol": "AAPL:XNAS"})

    def test_normalized_currency_identity_uses_existing_marker_order(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        result = self.service.execute_normalized(asset_id = "USD", currency = "EUR", asset_type = AssetType.fiat)

        self.assertEqual(result.asset, "USD")
        self.assertEqual(result.unit_price, 0.85)
        self.assertEqual(self.http.requests[0][1]["params"], {"format": "json", "from": "USD", "to": "EUR", "amount": "1.0"})

    def test_non_stock_result_omits_stock_metadata_from_dict(self):
        self.http.responses[self.fiat_url].append(stubs.external.http_json_response(stubs.external.fiat_exchange_response()))

        result = self.service.execute("USD", "EUR").as_dict()

        self.assertEqual(result, {
            "asset": "USD",
            "asset_type": AssetType.fiat,
            "amount": 1.0,
            "currency": "EUR",
            "unit_price": 0.85,
            "value": 0.85,
        })

    def test_invalid_explicit_asset_type_is_structured(self):
        with self.assertRaises(ValidationError) as context:
            self.service.execute("AAPL", "USD", asset_type = "commodity")

        self.assertEqual(context.exception.error_code, INVALID_ASSET_TYPE)
        self.assertEqual(self.http.requests, [])

    def test_invalid_amount_is_structured(self):
        for amount in ("many", float("nan"), float("inf")):
            with self.subTest(amount = amount):
                with self.assertRaises(ValidationError) as context:
                    self.service.execute("USD", "EUR", amount = amount)

                self.assertEqual(context.exception.error_code, INVALID_ASSET_AMOUNT)
        self.assertEqual(self.http.requests, [])

    def test_invalid_requested_currency_is_structured(self):
        with self.assertRaises(ValidationError) as context:
            self.service.execute("AAPL", "INVALID", asset_type = "stock")

        self.assertEqual(context.exception.error_code, INVALID_CURRENCY)
        self.assertEqual(self.http.requests, [])
