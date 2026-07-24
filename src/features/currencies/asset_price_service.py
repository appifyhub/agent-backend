from math import isfinite

from di.di import DI
from features.currencies.asset_price import AssetPrice, AssetType, StockQuote
from features.currencies.supported_currencies import SUPPORTED_CRYPTO, SUPPORTED_FIAT
from util import log
from util.error_codes import INVALID_ASSET_AMOUNT, INVALID_ASSET_TYPE, INVALID_CURRENCY
from util.errors import ValidationError


class AssetPriceService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def execute(
        self,
        asset: str,
        currency: str,
        asset_type: str | AssetType | None = None,
        amount: float = 1.0,
        force: bool = False,
    ) -> AssetPrice:
        normalized_asset = asset.strip().upper()
        normalized_currency = currency.strip().upper()

        try:
            normalized_amount = float(amount)
        except (TypeError, ValueError) as e:
            raise ValidationError("Asset amount must be numeric", INVALID_ASSET_AMOUNT) from e
        if not isfinite(normalized_amount):
            raise ValidationError("Asset amount must be a finite number", INVALID_ASSET_AMOUNT)
        if normalized_currency not in SUPPORTED_FIAT and normalized_currency not in SUPPORTED_CRYPTO:
            raise ValidationError(f"Unsupported currency: {normalized_currency}", INVALID_CURRENCY)
        log.t(f"Fetching price for {normalized_amount} {normalized_asset} in {normalized_currency}")

        resolved_type = self.__resolve_asset_type(normalized_asset, asset_type)
        match resolved_type:
            case AssetType.stock:
                log.t(f"Asset {normalized_asset} resolved as stock, fetching quote")
                quote = self.__di.stock_quote_fetcher.execute(normalized_asset, force = force)
                return self.__stock_price(quote, normalized_currency, normalized_amount, force)
            case AssetType.fiat | AssetType.crypto:
                log.t(f"Asset {normalized_asset} resolved as {resolved_type.value}, fetching exchange rate")
                result = self.__di.exchange_rate_fetcher.execute(normalized_asset, normalized_currency, normalized_amount, force = force)  # noqa: E501
                return AssetPrice(
                    asset = normalized_asset,
                    asset_type = resolved_type,
                    amount = normalized_amount,
                    currency = normalized_currency,
                    unit_price = result["rate"],
                    value = result["value"],
                )

    @staticmethod
    def __resolve_asset_type(asset: str, asset_type: str | AssetType | None) -> AssetType:
        if asset_type is not None:
            try:
                return AssetType(asset_type.strip().lower() if isinstance(asset_type, str) else asset_type)
            except ValueError as e:
                raise ValidationError(f"Unsupported asset type: {asset_type}. Supported types are fiat, crypto, and stock", INVALID_ASSET_TYPE) from e  # noqa: E501
        if asset in SUPPORTED_FIAT:
            return AssetType.fiat
        if asset in SUPPORTED_CRYPTO:
            return AssetType.crypto
        return AssetType.stock

    def __stock_price(self, quote: StockQuote, currency: str, amount: float, force: bool) -> AssetPrice:
        unit_price: float = quote.native_price
        if quote.native_currency != currency:
            conversion = self.__di.exchange_rate_fetcher.execute(quote.native_currency, currency, force = force)
            unit_price *= conversion["rate"]
        log.t(f"Stock quote for {quote.symbol} in {currency}: unit price = {unit_price}, amount = {amount}, value = {unit_price * amount}")  # noqa: E501

        return AssetPrice(
            asset = quote.identity,
            asset_type = AssetType.stock,
            amount = amount,
            currency = currency,
            unit_price = unit_price,
            value = unit_price * amount,
            provider = quote.provider,
            symbol = quote.symbol,
            native_currency = quote.native_currency,
            native_price = quote.native_price,
            name = quote.name,
            exchange = quote.exchange,
            mic_code = quote.mic_code,
            timestamp = quote.timestamp,
            is_market_open = quote.is_market_open,
            previous_close = quote.previous_close,
            change = quote.change,
            percent_change = quote.percent_change,
        )
