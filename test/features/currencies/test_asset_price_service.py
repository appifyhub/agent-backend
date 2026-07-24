import unittest
from unittest.mock import MagicMock

from di.di import DI
from features.currencies.asset_price import AssetType, StockQuote
from features.currencies.asset_price_service import AssetPriceService
from features.currencies.exchange_rate_fetcher import ExchangeRateFetcher
from features.currencies.stock_quote_fetcher import StockQuoteFetcher
from util.error_codes import INVALID_ASSET_AMOUNT, INVALID_ASSET_TYPE, INVALID_CURRENCY
from util.errors import ValidationError


class AssetPriceServiceTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = MagicMock(spec = DI)
        self.mock_di.exchange_rate_fetcher = MagicMock(spec = ExchangeRateFetcher)
        self.mock_di.stock_quote_fetcher = MagicMock(spec = StockQuoteFetcher)
        self.service = AssetPriceService(self.mock_di)
        self.stock_quote = StockQuote(
            symbol = "AAPL",
            name = "Apple Inc.",
            exchange = "NASDAQ",
            mic_code = "XNAS",
            native_currency = "USD",
            native_price = 210.5,
            timestamp = 1_753_352_400,
            is_market_open = True,
            previous_close = 208.75,
            change = 1.75,
            percent_change = 0.8383,
            provider = "twelve-data",
        )

    def test_fiat_inference_normalizes_markers_and_preserves_amount(self):
        self.mock_di.exchange_rate_fetcher.execute.return_value = {
            "rate": 0.85,
            "value": 212.5,
        }

        result = self.service.execute(" usd ", " eur ", amount = 250)

        self.assertEqual(result.asset, "USD")
        self.assertEqual(result.asset_type, AssetType.fiat)
        self.assertEqual(result.amount, 250)
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.unit_price, 0.85)
        self.assertEqual(result.value, 212.5)
        self.mock_di.exchange_rate_fetcher.execute.assert_called_once_with(
            "USD",
            "EUR",
            250,
            force = False,
        )
        self.mock_di.stock_quote_fetcher.execute.assert_not_called()

    def test_crypto_inference_routes_to_exchange_rate_fetcher(self):
        self.mock_di.exchange_rate_fetcher.execute.return_value = {
            "rate": 100000,
            "value": 200000,
        }

        result = self.service.execute("btc", "usd", amount = 2, force = True)

        self.assertEqual(result.asset_type, AssetType.crypto)
        self.mock_di.exchange_rate_fetcher.execute.assert_called_once_with(
            "BTC",
            "USD",
            2,
            force = True,
        )
        self.mock_di.stock_quote_fetcher.execute.assert_not_called()

    def test_omitted_type_uses_crypto_for_aapl_collision(self):
        self.mock_di.exchange_rate_fetcher.execute.return_value = {
            "rate": 0.01,
            "value": 0.01,
        }

        result = self.service.execute("AAPL", "USD")

        self.assertEqual(result.asset_type, AssetType.crypto)
        self.mock_di.exchange_rate_fetcher.execute.assert_called_once()
        self.mock_di.stock_quote_fetcher.execute.assert_not_called()

    def test_explicit_stock_overrides_aapl_collision(self):
        self.mock_di.stock_quote_fetcher.execute.return_value = self.stock_quote

        result = self.service.execute(" aapl ", " usd ", asset_type = " STOCK ")

        self.assertEqual(result.asset_type, AssetType.stock)
        self.assertEqual(result.asset, "XNAS:AAPL")
        self.mock_di.stock_quote_fetcher.execute.assert_called_once_with("AAPL", force = False)
        self.mock_di.exchange_rate_fetcher.execute.assert_not_called()

    def test_unknown_marker_is_inferred_as_stock(self):
        quote = StockQuote(
            symbol = "BRK.B",
            exchange = "NYSE",
            native_currency = "USD",
            native_price = 500,
            timestamp = 1_753_352_400,
            is_market_open = False,
            provider = "twelve-data",
        )
        self.mock_di.stock_quote_fetcher.execute.return_value = quote

        result = self.service.execute("brk.b", "usd")

        self.assertEqual(result.asset_type, AssetType.stock)
        self.assertEqual(result.asset, "NYSE:BRK.B")

    def test_native_stock_price_preserves_metadata_and_calculates_amount(self):
        self.mock_di.stock_quote_fetcher.execute.return_value = self.stock_quote

        result = self.service.execute("AAPL", "USD", asset_type = AssetType.stock, amount = 3)

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
        self.mock_di.exchange_rate_fetcher.execute.assert_not_called()

        serialized = result.as_dict()
        self.assertNotIn("timestamp", serialized)
        self.assertEqual(serialized["datetime"], "2025-07-24T10:20:00+00:00")

    def test_stock_price_converts_from_native_currency_and_propagates_force(self):
        self.mock_di.stock_quote_fetcher.execute.return_value = self.stock_quote
        self.mock_di.exchange_rate_fetcher.execute.return_value = {
            "rate": 0.8,
            "value": 0.8,
        }

        result = self.service.execute(
            "AAPL",
            "EUR",
            asset_type = "stock",
            amount = 2,
            force = True,
        )

        self.assertEqual(result.unit_price, 168.4)
        self.assertEqual(result.value, 336.8)
        self.assertEqual(result.native_price, 210.5)
        self.mock_di.stock_quote_fetcher.execute.assert_called_once_with("AAPL", force = True)
        self.mock_di.exchange_rate_fetcher.execute.assert_called_once_with(
            "USD",
            "EUR",
            force = True,
        )

    def test_non_stock_result_omits_stock_metadata_from_dict(self):
        self.mock_di.exchange_rate_fetcher.execute.return_value = {
            "rate": 0.85,
            "value": 0.85,
        }

        result = self.service.execute("USD", "EUR").as_dict()

        self.assertEqual(
            result,
            {
                "asset": "USD",
                "asset_type": AssetType.fiat,
                "amount": 1.0,
                "currency": "EUR",
                "unit_price": 0.85,
                "value": 0.85,
            },
        )

    def test_invalid_explicit_asset_type_is_structured(self):
        with self.assertRaises(ValidationError) as ctx:
            self.service.execute("AAPL", "USD", asset_type = "commodity")

        self.assertEqual(ctx.exception.error_code, INVALID_ASSET_TYPE)
        self.mock_di.exchange_rate_fetcher.execute.assert_not_called()
        self.mock_di.stock_quote_fetcher.execute.assert_not_called()

    def test_invalid_amount_is_structured(self):
        for amount in ("many", float("nan"), float("inf")):
            with self.subTest(amount = amount):
                with self.assertRaises(ValidationError) as ctx:
                    self.service.execute("USD", "EUR", amount = amount)

                self.assertEqual(ctx.exception.error_code, INVALID_ASSET_AMOUNT)

    def test_invalid_requested_currency_is_structured(self):
        with self.assertRaises(ValidationError) as ctx:
            self.service.execute("AAPL", "INVALID", asset_type = "stock")

        self.assertEqual(ctx.exception.error_code, INVALID_CURRENCY)
        self.mock_di.stock_quote_fetcher.execute.assert_not_called()
