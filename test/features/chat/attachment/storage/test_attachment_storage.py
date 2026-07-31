import io
import unittest
from pathlib import Path
from uuid import UUID

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.attachment_storage import AttachmentStorage


class _StubAttachmentStorage(AttachmentStorage):

    def __init__(self, content: bytes):
        self.stream = io.BytesIO(content)

    def open(self, _: ChatAttachment) -> io.BytesIO:
        return self.stream


class AttachmentStorageTest(unittest.TestCase):

    def setUp(self):
        self.attachment = ChatAttachment(
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 2),
            extension = "mp4",
            mime_type = "video/mp4",
        )

    def test_temporary_path_copies_content_closes_stream_and_removes_file(self):
        storage = _StubAttachmentStorage(b"video-bytes")

        with storage.temporary_path(self.attachment) as temporary_path:
            self.assertTrue(storage.stream.closed)
            self.assertTrue(temporary_path.endswith(".mp4"))
            self.assertEqual(Path(temporary_path).read_bytes(), b"video-bytes")

        self.assertFalse(Path(temporary_path).exists())

    def test_temporary_path_removes_file_after_consumer_failure(self):
        storage = _StubAttachmentStorage(b"video-bytes")
        temporary_path: str | None = None

        with self.assertRaisesRegex(RuntimeError, "consumer failed"):
            with storage.temporary_path(self.attachment) as temporary_path:
                raise RuntimeError("consumer failed")

        self.assertIsNotNone(temporary_path)
        self.assertFalse(Path(temporary_path).exists())
