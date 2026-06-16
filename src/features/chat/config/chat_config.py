from dataclasses import dataclass
from uuid import UUID

from db.model.chat_config import ChatConfigDB


@dataclass(kw_only = True)
class ChatConfig:

    chat_id: UUID | None = None
    external_id: str | None = None
    language_iso_code: str | None = None
    language_name: str | None = None
    title: str | None = None
    is_private: bool = True
    reply_chance_percent: int = 100
    release_notifications: ChatConfigDB.ReleaseNotifications = ChatConfigDB.ReleaseNotifications.major
    media_mode: ChatConfigDB.MediaMode = ChatConfigDB.MediaMode.photo
    chat_type: ChatConfigDB.ChatType
