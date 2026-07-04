from pathlib import Path, PurePosixPath
from typing import BinaryIO

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from util.error_codes import INVALID_ATTACHMENT_OPERATION
from util.errors import ValidationError

LOCAL_ATTACHMENT_STORAGE_ROOT = Path(".local/s3")


class LocalAttachmentStorage:

    __root: Path

    def __init__(self, root: Path = LOCAL_ATTACHMENT_STORAGE_ROOT):
        self.__root = root

    def ensure_ready(self) -> None:
        self.__root.mkdir(parents = True, exist_ok = True)

    def put(self, metadata: ChatMessageAttachment, content: bytes) -> None:
        path = self.__path_for(metadata.uri)
        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_bytes(content)

    def open(self, metadata: ChatMessageAttachment) -> BinaryIO:
        return self.__path_for(metadata.uri).open("rb")

    def delete(self, metadata: ChatMessageAttachment) -> None:
        path = self.__path_for(metadata.uri)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def __path_for(self, key: str) -> Path:
        parts = PurePosixPath(key).parts
        if not key or key.startswith("/") or ".." in parts:
            raise ValidationError("Invalid attachment storage key", INVALID_ATTACHMENT_OPERATION)
        return self.__root.joinpath(*parts)
