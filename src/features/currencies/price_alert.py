from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from features.currencies.asset_price import AssetType


@dataclass(kw_only = True)
class PriceAlert:
    chat_id: UUID
    owner_id: UUID
    asset_type: AssetType
    asset_id: str
    currency: str
    threshold_percent: int
    last_price: float
    last_price_time: datetime = field(default_factory = datetime.now)
