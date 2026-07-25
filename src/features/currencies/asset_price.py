from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

PRICE_CACHE_TTL = timedelta(minutes = 9)


class AssetType(StrEnum):

    fiat = "fiat"
    crypto = "crypto"
    stock = "stock"


@dataclass(frozen = True, kw_only = True)
class StockQuote:
    symbol: str
    native_currency: str
    native_price: float
    timestamp: int
    is_market_open: bool | None
    provider: str
    name: str | None = None
    exchange: str | None = None
    mic_code: str | None = None
    previous_close: float | None = None
    change: float | None = None
    percent_change: float | None = None
    requested_qualifier: str | None = None

    @property
    def identity(self) -> str:
        qualifier = self.mic_code or self.exchange or self.requested_qualifier
        return f"{qualifier}:{self.symbol}" if qualifier else self.symbol


@dataclass(frozen = True, kw_only = True)
class AssetPrice:
    asset: str
    asset_type: AssetType
    amount: float
    currency: str
    unit_price: float
    value: float
    provider: str | None = None
    symbol: str | None = None
    native_currency: str | None = None
    native_price: float | None = None
    name: str | None = None
    exchange: str | None = None
    mic_code: str | None = None
    timestamp: int | None = None
    is_market_open: bool | None = None
    previous_close: float | None = None
    change: float | None = None
    percent_change: float | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {key: value for key, value in asdict(self).items() if value is not None}
        timestamp = result.pop("timestamp", None)
        if timestamp is not None:
            result["datetime"] = datetime.fromtimestamp(timestamp, tz = timezone.utc).isoformat()
        return result
