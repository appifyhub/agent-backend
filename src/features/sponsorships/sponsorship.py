from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(kw_only = True)
class Sponsorship:
    sponsor_id: UUID
    receiver_id: UUID
    sponsored_at: datetime = field(default_factory = datetime.now)
    accepted_at: datetime | None = None
