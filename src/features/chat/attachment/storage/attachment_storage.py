from dataclasses import dataclass
from typing import BinaryIO, ClassVar, Protocol

from features.chat.attachment.chat_attachment import ChatAttachment


@dataclass(frozen = True)
class PublicAttachment:
    id: str
    url: str
    valid_until: int


class AttachmentStorage(Protocol):

    SERVES_PUBLIC_URLS: ClassVar[bool]

    @classmethod
    def can_be_used(cls) -> bool: ...

    def ensure_ready(self) -> None: ...

    def owns_uri(self, uri: str | None) -> bool: ...

    def put(self, metadata: ChatAttachment, content: bytes) -> str: ...

    def open(self, metadata: ChatAttachment) -> BinaryIO: ...

    def delete(self, metadata: ChatAttachment) -> None: ...

    def public_attachment_for(self, metadata: ChatAttachment) -> PublicAttachment: ...
