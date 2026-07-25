from math import isfinite
from typing import Any

from di.di import DI
from features.currencies.asset_price import PRICE_CACHE_TTL, StockQuote
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import TWELVE_DATA
from features.external_tools.intelligence_presets import default_tool_for
from util.error_codes import (
    INVALID_STOCK_SYMBOL,
    STOCK_QUOTE_FAILED,
    STOCK_QUOTE_NOT_FOUND,
    STOCK_QUOTE_RATE_LIMITED,
)
from util.errors import ExternalServiceError, NotFoundError, RateLimitError, ValidationError

API_URL = "https://api.twelvedata.com/quote"


class StockQuoteFetcher:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def execute(self, symbol: str, force: bool = False) -> StockQuote:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValidationError("A stock symbol is required", INVALID_STOCK_SYMBOL)

        configured_tool = self.__di.tool_choice_resolver.require_tool(ToolType.api_stock_quote, default_tool_for(ToolType.api_stock_quote))  # noqa: E501
        fetcher = self.__di.tracked_web_fetcher(
            configured_tool = configured_tool,
            url = API_URL,
            headers = {
                "Accept": "application/json",
                "Authorization": f"apikey {configured_tool.token.get_secret_value()}",
            },
            params = {"symbol": normalized_symbol},
            cache_ttl_json = PRICE_CACHE_TTL,
            force = force,
        )
        response = fetcher.fetch_json()
        error_response = fetcher.error_json
        if response is None and error_response is not None:
            self.__raise_provider_error(error_response, fetcher.status_code)
        if response is None or not isinstance(response, dict) or not response:
            raise ExternalServiceError("Twelve Data returned an empty or invalid stock quote", STOCK_QUOTE_FAILED)
        if response.get("status") == "error" or "code" in response and "message" in response:
            self.__raise_provider_error(response, fetcher.status_code)

        return self.__parse_quote(response, normalized_symbol)

    @staticmethod
    def __raise_provider_error(response: dict[str, Any], status_code: int | None) -> None:
        message = str(response.get("message") or "Twelve Data could not provide this stock quote")
        raw_code = response.get("code", status_code)
        try:
            code = int(raw_code) if raw_code is not None else status_code
        except (TypeError, ValueError):
            code = status_code

        normalized_message = message.lower()
        if code == 429 or status_code == 429:
            raise RateLimitError(message, STOCK_QUOTE_RATE_LIMITED)
        if "available starting with" in normalized_message or "upgrade" in normalized_message:
            raise ExternalServiceError(message, STOCK_QUOTE_FAILED)
        if code == 404 or status_code == 404 or "not found" in normalized_message:
            raise NotFoundError(message, STOCK_QUOTE_NOT_FOUND)
        if code in (400, 422):
            raise ValidationError(message, INVALID_STOCK_SYMBOL)
        raise ExternalServiceError(message, STOCK_QUOTE_FAILED)

    @staticmethod
    def __parse_quote(response: dict[str, Any], requested_symbol: str) -> StockQuote:
        required_fields = ("symbol", "currency", "close", "timestamp", "is_market_open")
        missing_fields = [field for field in required_fields if response.get(field) is None]
        if missing_fields:
            fields = ", ".join(missing_fields)
            raise ExternalServiceError(f"Twelve Data stock quote is missing required fields: {fields}", STOCK_QUOTE_FAILED)

        try:
            symbol = str(response["symbol"]).strip().upper()
            native_currency = str(response["currency"]).strip().upper()
            native_price = float(response["close"])
            timestamp = int(response["timestamp"])
            previous_close = StockQuoteFetcher.__optional_float(response.get("previous_close"))
            change = StockQuoteFetcher.__optional_float(response.get("change"))
            percent_change = StockQuoteFetcher.__optional_float(response.get("percent_change"))
        except (TypeError, ValueError, KeyError) as e:
            raise ExternalServiceError("Twelve Data returned a malformed stock quote", STOCK_QUOTE_FAILED) from e

        if not symbol or not native_currency:
            raise ExternalServiceError("Twelve Data returned a malformed stock quote", STOCK_QUOTE_FAILED)
        numeric_values = (native_price, previous_close, change, percent_change)
        if any(value is not None and not isfinite(value) for value in numeric_values):
            raise ExternalServiceError("Twelve Data returned non-finite stock quote values", STOCK_QUOTE_FAILED)
        if not isinstance(response["is_market_open"], bool):
            raise ExternalServiceError("Twelve Data returned a malformed market-open status", STOCK_QUOTE_FAILED)

        requested_qualifier = requested_symbol.split(":", maxsplit = 1)[1] if ":" in requested_symbol else None
        return StockQuote(
            symbol = symbol,
            name = StockQuoteFetcher.__optional_string(response.get("name")),
            exchange = StockQuoteFetcher.__optional_string(response.get("exchange")),
            mic_code = StockQuoteFetcher.__optional_string(response.get("mic_code")),
            native_currency = native_currency,
            native_price = native_price,
            timestamp = timestamp,
            is_market_open = response["is_market_open"],
            previous_close = previous_close,
            change = change,
            percent_change = percent_change,
            provider = TWELVE_DATA.id,
            requested_qualifier = requested_qualifier,
        )

    @staticmethod
    def __optional_float(value: Any) -> float | None:
        return float(value) if value is not None and value != "" else None

    @staticmethod
    def __optional_string(value: Any) -> str | None:
        return str(value) if value is not None and value != "" else None
