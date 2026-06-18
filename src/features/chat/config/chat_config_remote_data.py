from dataclasses import dataclass

from db.model.chat_config import ChatConfigDB


@dataclass(kw_only = True)
class ChatConfigRemoteData:
    external_id: str
    chat_type: ChatConfigDB.ChatType
    title: str | None = None
    is_private: bool | None = None
    language_iso_code: str | None = None
