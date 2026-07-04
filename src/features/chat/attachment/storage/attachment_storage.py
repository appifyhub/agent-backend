from typing import BinaryIO, Protocol

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment


class AttachmentStorage(Protocol):

    def ensure_ready(self) -> None: ...

    def put(self, metadata: ChatMessageAttachment, content: bytes) -> None: ...

    def open(self, metadata: ChatMessageAttachment) -> BinaryIO: ...

    def delete(self, metadata: ChatMessageAttachment) -> None: ...
