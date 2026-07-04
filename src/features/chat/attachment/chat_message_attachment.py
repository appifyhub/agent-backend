from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from util.functions import generate_short_uuid


@dataclass(kw_only = True)
class ChatMessageAttachment:

    chat_id: UUID
    message_id: str
    id: str = field(default_factory = generate_short_uuid)
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

    @property
    def uri(self) -> str:
        suffix = f".{self.extension}" if self.extension else ""
        return f"chats/{self.chat_id}/messages/{self.message_id}/attachments/{self.id}{suffix}"
