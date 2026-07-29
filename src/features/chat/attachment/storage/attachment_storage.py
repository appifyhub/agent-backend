import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import BinaryIO, ClassVar, Generator, Protocol

from features.chat.attachment.chat_attachment import ChatAttachment
from util.functions import delete_file_safe


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

    @contextmanager
    def temporary_path(self, metadata: ChatAttachment) -> Generator[str, None, None]:
        temp_path: str | None = None
        try:
            suffix = f".{metadata.extension}" if metadata.extension else ""
            with NamedTemporaryFile(delete = False, suffix = suffix) as temp_file:
                temp_path = temp_file.name
                with self.open(metadata) as attachment_stream:
                    shutil.copyfileobj(attachment_stream, temp_file)
            yield temp_path
        finally:
            delete_file_safe(temp_path)

    def delete(self, metadata: ChatAttachment) -> None: ...

    def public_attachment_for(self, metadata: ChatAttachment) -> PublicAttachment: ...
