from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen = True, kw_only = True)
class ScheduledChatMessageBurst:
    chat_id: UUID
    author_id: UUID
    message_count: int
    wait_seconds: float


@dataclass(frozen = True, kw_only = True)
class ClaimedChatMessageBurst:
    chat_id: UUID
    author_id: UUID
    message_count: int
    last_message_sent_at: datetime
    last_message_ingestion_order: int
    is_addressed: bool
