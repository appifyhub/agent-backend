from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(kw_only = True)
class PriceAlert:
    chat_id: UUID
    owner_id: UUID
    base_currency: str
    desired_currency: str
    threshold_percent: int
    last_price: float
    last_price_time: datetime = field(default_factory = datetime.now)
