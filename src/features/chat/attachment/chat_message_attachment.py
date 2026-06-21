from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(kw_only = True)
class ChatMessageAttachment:

    chat_id: UUID
    message_id: str
    id: str | None = None
    external_id: str | None = None
    size: int | None = None
    last_url: str | None = None
    last_url_until: int | None = None
    extension: str | None = None
    mime_type: str | None = None

    @property
    def has_stale_data(self) -> bool:
        is_missing_url = not self.last_url
        expiration_timestamp = self.last_url_until or 0
        is_url_expired = expiration_timestamp <= int(datetime.now().timestamp())
        return is_missing_url or is_url_expired
