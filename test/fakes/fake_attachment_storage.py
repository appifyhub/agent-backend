from pathlib import Path
from typing import BinaryIO

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.local_attachment_storage import LocalAttachmentStorage


class RecordingAttachmentStorage(LocalAttachmentStorage):

    ready_calls: int
    opened_streams: list[BinaryIO]

    def __init__(self, root: Path):
        super().__init__(root = root)
        self.ready_calls = 0
        self.opened_streams: list[BinaryIO] = []

    def ensure_ready(self) -> None:
        super().ensure_ready()
        self.ready_calls += 1

    def open(self, metadata: ChatAttachment) -> BinaryIO:
        stream = super().open(metadata)
        self.opened_streams.append(stream)
        return stream
