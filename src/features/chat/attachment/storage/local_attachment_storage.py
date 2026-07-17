from pathlib import Path, PurePosixPath
from typing import BinaryIO

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.storage.attachment_storage import AttachmentStorage, PublicAttachment
from util.error_codes import INVALID_ATTACHMENT_OPERATION
from util.errors import InternalError, ValidationError

LOCAL_ATTACHMENT_STORAGE_ROOT = Path(".local/s3")


class LocalAttachmentStorage(AttachmentStorage):

    SERVES_PUBLIC_URLS = False

    __root: Path

    def __init__(self, root: Path = LOCAL_ATTACHMENT_STORAGE_ROOT):
        self.__root = root

    @classmethod
    def can_be_used(cls) -> bool:
        return True

    def ensure_ready(self) -> None:
        self.__root.mkdir(parents = True, exist_ok = True)

    def owns_uri(self, uri: str | None) -> bool:
        return bool(uri) and uri.startswith(f"file://{self.__root}/")

    def put(self, metadata: ChatMessageAttachment, content: bytes) -> str:
        path = self.__path_for(metadata.uri)
        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_bytes(content)
        return f"file://{self.__root}/{metadata.uri}"

    def open(self, metadata: ChatMessageAttachment) -> BinaryIO:
        return self.__path_for(metadata.uri).open("rb")

    def delete(self, metadata: ChatMessageAttachment) -> None:
        path = self.__path_for(metadata.uri)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def public_attachment_for(self, _: ChatMessageAttachment) -> PublicAttachment:
        raise InternalError("Local attachment storage does not serve public URLs", INVALID_ATTACHMENT_OPERATION)

    def __path_for(self, key: str) -> Path:
        parts = PurePosixPath(key).parts
        if not key or key.startswith("/") or ".." in parts:
            raise ValidationError("Invalid attachment storage key", INVALID_ATTACHMENT_OPERATION)
        return self.__root.joinpath(*parts)
