from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(kw_only = True)
class ChatMessage:

    chat_id: UUID
    message_id: str
    text: str
    author_id: UUID | None = None
    sent_at: datetime = field(default_factory = datetime.now)
