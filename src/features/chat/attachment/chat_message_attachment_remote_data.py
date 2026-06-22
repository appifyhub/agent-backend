from dataclasses import dataclass


@dataclass(kw_only = True)
class ChatMessageAttachmentRemoteData:

    external_id: str
    message_id: str
    size: int | None = None
    last_url: str | None = None
    last_url_until: int | None = None
    extension: str | None = None
    mime_type: str | None = None
