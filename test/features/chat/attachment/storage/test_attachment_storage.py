from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fakes.fake_attachment_storage import RecordingAttachmentStorage
from stubs import domain

from features.chat.attachment.chat_attachment import ChatAttachment
from util.error_codes import INVALID_ATTACHMENT_OPERATION
from util.errors import InternalError


class AttachmentStorageTest(TestCase):

    storage: RecordingAttachmentStorage
    attachment: ChatAttachment

    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.storage = RecordingAttachmentStorage(root)
        self.attachment = domain.chat_attachment(extension = "mp4")
        self.storage.put(self.attachment, b"video-bytes")

    def test_temporary_path_copies_content_closes_stream_and_removes_file(self):
        with self.storage.temporary_path(self.attachment) as temporary_path:
            self.assertTrue(self.storage.opened_streams[0].closed)
            self.assertTrue(temporary_path.endswith(".mp4"))
            self.assertEqual(Path(temporary_path).read_bytes(), b"video-bytes")

        self.assertFalse(Path(temporary_path).exists())

    def test_temporary_path_removes_file_after_consumer_failure(self):
        temporary_path: str | None = None

        with self.assertRaisesRegex(InternalError, "consumer failed"):
            with self.storage.temporary_path(self.attachment) as temporary_path:
                raise InternalError("consumer failed", INVALID_ATTACHMENT_OPERATION)

        self.assertIsNotNone(temporary_path)
        self.assertFalse(Path(temporary_path).exists())
