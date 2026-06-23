from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only = True)
class ChatMessageRemoteData:

    message_id: str
    sent_at: datetime
    text: str
