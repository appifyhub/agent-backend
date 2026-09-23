import tempfile
import unittest
from pathlib import Path

import stubs

from features.chat.attachment.storage.local_attachment_storage import LocalAttachmentStorage
from util.errors import ValidationError


class LocalAttachmentStorageTest(unittest.TestCase):

    def test_declares_public_delivery_capability(self):
        self.assertFalse(LocalAttachmentStorage.SERVES_PUBLIC_URLS)

    def test_can_be_used_is_always_true(self):
        self.assertTrue(LocalAttachmentStorage.can_be_used())

    def test_owns_uri_recognizes_own_file_locator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storage = LocalAttachmentStorage(root)
            metadata = stubs.domain.chat_attachment()

            self.assertTrue(storage.owns_uri(f"file://{root}/{metadata.uri}"))
            self.assertFalse(storage.owns_uri(f"s3://the-agent/{metadata.uri}"))
            self.assertFalse(storage.owns_uri(None))
            self.assertFalse(storage.owns_uri(""))

    def test_put_open_and_delete_uses_local_storage_root(self):
        metadata = stubs.domain.chat_attachment()
        content = b"stored content"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storage = LocalAttachmentStorage(root)

            storage.ensure_ready()
            locator = storage.put(metadata, content)

            self.assertEqual(locator, f"file://{root}/{metadata.uri}")

            with storage.open(metadata) as stream:
                self.assertEqual(stream.read(), content)

            expected_path = root.joinpath(*metadata.uri.split("/"))
            self.assertTrue(expected_path.exists())

            storage.delete(metadata)
            storage.delete(metadata)

            self.assertFalse(expected_path.exists())

    def test_put_file_copies_content_without_removing_source(self):
        metadata = stubs.domain.chat_attachment()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).joinpath("storage")
            source = Path(temp_dir).joinpath("source.txt")
            source.write_bytes(b"stored content")
            storage = LocalAttachmentStorage(root)

            locator = storage.put_file(metadata, source)

            self.assertEqual(locator, f"file://{root}/{metadata.uri}")
            self.assertEqual(source.read_bytes(), b"stored content")
            with storage.open(metadata) as stream:
                self.assertEqual(stream.read(), b"stored content")

    def test_rejects_path_traversal_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalAttachmentStorage(Path(temp_dir))
            metadata = stubs.domain.chat_attachment(id = "../outside")

            with self.assertRaises(ValidationError):
                storage.put(metadata, b"content")
