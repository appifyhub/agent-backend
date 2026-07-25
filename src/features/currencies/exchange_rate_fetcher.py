import json
from datetime import datetime
from time import sleep
from typing import Any, Dict

from di.di import DI
from features.currencies.asset_price import PRICE_CACHE_TTL
from features.currencies.supported_currencies import SUPPORTED_CRYPTO, SUPPORTED_FIAT
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import CRYPTO_CURRENCY_EXCHANGE, FIAT_CURRENCY_EXCHANGE
from features.tools_cache.tools_cache import ToolsCache
from util import log
from util.error_codes import EXCHANGE_RATE_NOT_FOUND, INVALID_CURRENCY, UNSUPPORTED_CURRENCY_PAIR
from util.errors import NotFoundError, ValidationError

DEFAULT_FIAT = "USD"
CACHE_PREFIX = "exchange-rate-fetcher"
CACHE_TTL = PRICE_CACHE_TTL
RATE_LIMIT_DELAY_S = 1


class ExchangeRateFetcher:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def execute(
        self,
        base_currency_code: str,
        desired_currency_code: str,
        amount: float = 1.0,
        force: bool = False,
    ) -> Dict[str, Any]:
        def as_result(rate: float) -> dict[str, Any]:
            return {
                "from": base_currency_code,
                "to": desired_currency_code,
                "rate": rate,
                "amount": amount,
                "value": rate * amount,
            }

        log.d(f"Calculating conversion rate {base_currency_code}/{desired_currency_code} for {amount}")
        if base_currency_code == desired_currency_code:
            log.t("Returning the identity conversion rate")
            return as_result(1.0)

        is_base_fiat = base_currency_code in SUPPORTED_FIAT
        is_base_crypto = base_currency_code in SUPPORTED_CRYPTO and base_currency_code != DEFAULT_FIAT
        is_desired_fiat = desired_currency_code in SUPPORTED_FIAT
        is_desired_crypto = desired_currency_code in SUPPORTED_CRYPTO and desired_currency_code != DEFAULT_FIAT
        log.t(f"{base_currency_code} is {"F" if is_base_fiat else "C" if is_base_crypto else "??"}")
        log.t(f"{desired_currency_code} is {"F" if is_desired_fiat else "C" if is_desired_crypto else "??"}")

        if is_base_fiat and is_desired_fiat:
            log.t("Fetching fiat to fiat conversion rate")
            rate_of_one = self.get_fiat_conversion_rate(base_currency_code, desired_currency_code, force = force)
            return as_result(rate_of_one)
        elif is_base_crypto and is_desired_crypto:
            log.t("Fetching crypto to crypto conversion rate")
            rate_of_one = self.get_crypto_conversion_rate(base_currency_code, desired_currency_code, force = force)
            return as_result(rate_of_one)
        elif is_base_fiat and is_desired_crypto:
            # we traverse the exchange rate through the default fiat to get the final rate
            log.t("Fetching fiat to crypto conversion rate")
            base_fiat_rate_against_default_fiat = self.get_fiat_conversion_rate(base_currency_code, DEFAULT_FIAT, force = force)
            default_fiat_rate_against_crypto = self.get_crypto_conversion_rate(DEFAULT_FIAT, desired_currency_code, force = force)
            return as_result(base_fiat_rate_against_default_fiat * default_fiat_rate_against_crypto)
        elif is_base_crypto and is_desired_fiat:
            # basically the same as above, just in reverse
            log.t("Fetching crypto to fiat conversion rate")
            base_crypto_rate_against_default_fiat = self.get_crypto_conversion_rate(base_currency_code, DEFAULT_FIAT, force = force)  # noqa: E501
            default_fiat_rate_against_fiat = self.get_fiat_conversion_rate(DEFAULT_FIAT, desired_currency_code, force = force)
            return as_result(base_crypto_rate_against_default_fiat * default_fiat_rate_against_fiat)
        else:
            raise ValidationError(f"Unsupported currency conversion: {base_currency_code}/{desired_currency_code}", UNSUPPORTED_CURRENCY_PAIR)  # noqa: E501

    # when converting exchange rates, the inverse rule applies:  A / B = 1 / (B / A)
    def __get_cached_rate_of_one(self, base_currency_code: str, desired_currency_code: str) -> float | None:
        # let's check the direct requested conversion rate first
        log.t(f"Fetching cached rate for {base_currency_code}/{desired_currency_code}")
        cache_key = ToolsCache.create_key(CACHE_PREFIX, f"{base_currency_code}-{desired_currency_code}")
        log.t(f"    Cache key: '{cache_key}'")
        cache_entry = self.__di.tools_cache_repo.get(cache_key)
        if cache_entry:
            if not cache_entry.is_expired():
                log.t(f"Cache hit for direct conversion and key '{cache_key}'")
                return float(cache_entry.value)
            log.t(f"Cache expired for direct conversion and key '{cache_key}'")
        log.t(f"Cache miss for direct conversion and key '{cache_key}'")

        # now let's check for the inverse conversion rate
        log.t(f"Fetching cached inverse rate for {base_currency_code}/{desired_currency_code}")
        cache_key = ToolsCache.create_key(CACHE_PREFIX, f"{desired_currency_code}-{base_currency_code}")
        log.t(f"    Cache key: '{cache_key}'")
        cache_entry = self.__di.tools_cache_repo.get(cache_key)
        if cache_entry:
            if not cache_entry.is_expired():
                log.t(f"Cache hit for inverse conversion and key '{cache_key}'")
                return 1.0 / float(cache_entry.value)
            log.t(f"Cache expired for inverse conversion and key '{cache_key}'")
        log.t(f"Cache miss for inverse conversion and key '{cache_key}'")
        return None

    def __save_rate_to_cache(self, a: str, b: str, rate: float) -> None:
        key = ToolsCache.create_key(CACHE_PREFIX, f"{a}-{b}")
        self.__di.tools_cache_repo.save(ToolsCache(
            key = key,
            value = str(rate),
            expires_at = datetime.now() + CACHE_TTL,
        ))
        log.t(f"Cache updated for {a}/{b} and key '{key}'")

    def get_crypto_conversion_rate(self, base_currency_code: str, desired_currency_code: str, force: bool = False) -> float:
        log.t(f"Fetching crypto conversion rate {base_currency_code}/{desired_currency_code}")
        if base_currency_code not in SUPPORTED_CRYPTO and base_currency_code != DEFAULT_FIAT:
            raise ValidationError(f"Unsupported currency: {base_currency_code}", INVALID_CURRENCY)
        if desired_currency_code not in SUPPORTED_CRYPTO and desired_currency_code != DEFAULT_FIAT:
            raise ValidationError(f"Unsupported currency: {desired_currency_code}", INVALID_CURRENCY)

        if base_currency_code == desired_currency_code:
            return 1.0

        if not force:
            cached_rate = self.__get_cached_rate_of_one(base_currency_code, desired_currency_code)
            if cached_rate is not None:
                return cached_rate

        rate: float
        api_url = f"https://pro-api.coinmarketcap.com/{CRYPTO_CURRENCY_EXCHANGE.id.replace(".", "/")}"
        resolved = self.__di.access_token_resolver.require_access_token_for_tool(CRYPTO_CURRENCY_EXCHANGE)
        headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": resolved.token.get_secret_value()}
        crypto_tool: ConfiguredTool = ConfiguredTool(
            definition = CRYPTO_CURRENCY_EXCHANGE,
            token = resolved.token,
            purpose = ToolType.api_crypto_exchange,
            payer_id = resolved.payer_id,
            uses_credits = resolved.uses_credits,
        )

        if base_currency_code != DEFAULT_FIAT and desired_currency_code != DEFAULT_FIAT:
            # due to API limitations, we must traverse both cryptos through USD
            params_base = {"symbol": base_currency_code, "convert": DEFAULT_FIAT}
            sleep(RATE_LIMIT_DELAY_S)
            fetcher_base = self.__di.tracked_web_fetcher(crypto_tool, api_url, headers, params_base, cache_ttl_json = CACHE_TTL, force = force)  # noqa: E501
            response_base = fetcher_base.fetch_json() or {}

            params_desired = {"symbol": desired_currency_code, "convert": DEFAULT_FIAT}
            sleep(RATE_LIMIT_DELAY_S)
            fetcher_desired = self.__di.tracked_web_fetcher(crypto_tool, api_url, headers, params_desired, cache_ttl_json = CACHE_TTL, force = force)  # noqa: E501
            response_desired = fetcher_desired.fetch_json() or {}

            base_rate = float(response_base["data"][base_currency_code]["quote"][DEFAULT_FIAT]["price"])
            desired_rate = float(response_desired["data"][desired_currency_code]["quote"][DEFAULT_FIAT]["price"])
            rate = base_rate / desired_rate
        else:
            # one of the currencies is USD, we can fetch the rate directly
            symbol = desired_currency_code if base_currency_code == DEFAULT_FIAT else base_currency_code
            params = {"symbol": symbol, "convert": DEFAULT_FIAT}
            sleep(RATE_LIMIT_DELAY_S)
            fetcher = self.__di.tracked_web_fetcher(crypto_tool, api_url, headers, params, cache_ttl_json = CACHE_TTL, force = force)  # noqa: E501
            response = fetcher.fetch_json() or {}

            rate = float(response["data"][symbol]["quote"][DEFAULT_FIAT]["price"])
            if base_currency_code == DEFAULT_FIAT:
                rate = 1 / rate
        if rate:
            self.__save_rate_to_cache(base_currency_code, desired_currency_code, rate)
            return rate
        raise NotFoundError(f"No rate found for {base_currency_code}/{desired_currency_code}", EXCHANGE_RATE_NOT_FOUND)

    def get_fiat_conversion_rate(self, base_currency_code: str, desired_currency_code: str, force: bool = False) -> float:
        log.t(f"Fetching fiat conversion rate {base_currency_code}/{desired_currency_code}")
        if base_currency_code not in SUPPORTED_FIAT:
            raise ValidationError(f"Unsupported currency: {base_currency_code}", INVALID_CURRENCY)
        if desired_currency_code not in SUPPORTED_FIAT:
            raise ValidationError(f"Unsupported currency: {desired_currency_code}", INVALID_CURRENCY)

        if base_currency_code == desired_currency_code:
            return 1.0

        if not force:
            cached_rate = self.__get_cached_rate_of_one(base_currency_code, desired_currency_code)
            if cached_rate is not None:
                return cached_rate

        sleep(RATE_LIMIT_DELAY_S)
        api_url = f"https://{FIAT_CURRENCY_EXCHANGE.id}/currency/convert"
        params = {"format": "json", "from": base_currency_code, "to": desired_currency_code, "amount": "1.0"}
        resolved = self.__di.access_token_resolver.require_access_token_for_tool(FIAT_CURRENCY_EXCHANGE)
        headers = {"X-RapidAPI-Key": resolved.token.get_secret_value(), "X-RapidAPI-Host": FIAT_CURRENCY_EXCHANGE.id}
        fiat_tool: ConfiguredTool = ConfiguredTool(
            definition = FIAT_CURRENCY_EXCHANGE,
            token = resolved.token,
            purpose = ToolType.api_fiat_exchange,
            payer_id = resolved.payer_id,
            uses_credits = resolved.uses_credits,
        )

        fetcher = self.__di.tracked_web_fetcher(fiat_tool, api_url, headers, params, cache_ttl_json = CACHE_TTL, force = force)
        response = fetcher.fetch_json() or {}

        rate = float(response["rates"][desired_currency_code]["rate_for_amount"])
        if rate:
            self.__save_rate_to_cache(base_currency_code, desired_currency_code, rate)
            return rate
        raise NotFoundError(f"Invalid rate: {rate}; API: {FIAT_CURRENCY_EXCHANGE.id}; response data: {json.dumps(response)}", EXCHANGE_RATE_NOT_FOUND)  # noqa: E501
