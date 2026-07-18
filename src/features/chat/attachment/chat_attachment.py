from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from util.functions import generate_short_uuid


@dataclass(kw_only = True)
class ChatAttachment:

    id: str = field(default_factory = generate_short_uuid)
    chat_id: UUID
    uploader_user_id: UUID
    message_id: str | None = None
    external_id: str | None = None
    created_at: datetime = field(default_factory = datetime.now)
    size: int | None = None
    last_url: str | None = None
    extension: str | None = None
    mime_type: str | None = None

    @property
    def uri(self) -> str:
        suffix = f".{self.extension}" if self.extension else ""
        return f"chats/{self.chat_id}/attachments/{self.id}{suffix}"
