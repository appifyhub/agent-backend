from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fakes.s3_client import FakeS3Client
from pydantic import SecretStr
from stubs import domain, external
from util.di import FakeInterceptor, di_for_tests

from features.chat.attachment.storage.s3_attachment_storage import S3AttachmentStorage
from features.chat.attachment.storage.s3_client import S3Client
from util.config import config
from util.errors import ExternalServiceError


class S3AttachmentStorageTest(TestCase):

    def test_declares_public_delivery_capability(self):
        self.assertFalse(S3AttachmentStorage.SERVES_PUBLIC_URLS)

    def setUp(self):
        for name, value in {
            "s3_base_url": "http://s3.invalid",
            "s3_region": "eu-central-1",
            "s3_bucket": "the-agent",
            "s3_access_key": SecretStr("access"),
            "s3_secret_key": SecretStr("secret"),
        }.items():
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)

    def test_can_be_used_requires_complete_config(self):
        self.assertTrue(S3AttachmentStorage.can_be_used())
        for name in ("s3_base_url", "s3_region", "s3_bucket", "s3_access_key", "s3_secret_key"):
            with self.subTest(missing_field = name):
                previous = getattr(config, name)
                try:
                    setattr(config, name, SecretStr("") if isinstance(previous, SecretStr) else "")
                    self.assertFalse(S3AttachmentStorage.can_be_used())
                finally:
                    setattr(config, name, previous)

    def test_owns_uri_recognizes_own_bucket_locator(self):
        storage = self.__storage(FakeS3Client())
        metadata = domain.chat_attachment()

        self.assertTrue(storage.owns_uri(f"s3://the-agent/{metadata.uri}"))
        self.assertFalse(storage.owns_uri("s3://other-bucket/chats/x"))
        self.assertFalse(storage.owns_uri("file:///tmp/chats/x"))
        self.assertFalse(storage.owns_uri(None))
        self.assertFalse(storage.owns_uri(""))

    def test_ensure_ready_accepts_existing_bucket(self):
        client = FakeS3Client()
        storage = self.__storage(client)

        storage.ensure_ready()

        self.assertEqual(client.calls, [("head_bucket", {"Bucket": "the-agent"})])

    def test_ensure_ready_creates_missing_bucket(self):
        client = FakeS3Client()
        storage = self.__storage(client)
        client.buckets.clear()

        storage.ensure_ready()

        self.assertEqual(
            client.calls,
            [
                ("head_bucket", {"Bucket": "the-agent"}),
                (
                    "create_bucket",
                    {"Bucket": "the-agent"},
                ),
            ],
        )

    def test_put_open_and_delete_use_configured_bucket(self):
        client = FakeS3Client()
        storage = self.__storage(client)
        metadata = domain.chat_attachment(mime_type = "text/plain")

        storage.put(metadata, b"stored content")
        with storage.open(metadata) as stream:
            self.assertEqual(stream.read(), b"stored content")
        storage.delete(metadata)

        self.assertNotIn(("the-agent", metadata.uri), client.objects)
        self.assertEqual(
            client.calls,
            [
                (
                    "put_object",
                    {
                        "Bucket": "the-agent",
                        "Key": metadata.uri,
                        "Body": b"stored content",
                        "ContentType": "text/plain",
                    },
                ),
                ("get_object", {"Bucket": "the-agent", "Key": metadata.uri}),
                ("delete_object", {"Bucket": "the-agent", "Key": metadata.uri}),
            ],
        )

    def test_put_omits_content_type_when_canonical_mime_type_is_missing(self):
        client = FakeS3Client()
        storage = self.__storage(client)
        metadata = domain.chat_attachment(mime_type = None, extension = "png")

        storage.put(metadata, b"stored content")

        self.assertEqual(
            client.calls,
            [
                (
                    "put_object",
                    {
                        "Bucket": "the-agent",
                        "Key": metadata.uri,
                        "Body": b"stored content",
                    },
                ),
            ],
        )

    def test_put_file_uploads_path_with_content_type(self):
        client = FakeS3Client()
        storage = self.__storage(client)
        metadata = domain.chat_attachment(mime_type = "video/mp4", extension = "mp4")

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir).joinpath("source.mp4")
            source.write_bytes(b"video")

            locator = storage.put_file(metadata, source)

        self.assertEqual(locator, f"s3://the-agent/{metadata.uri}")
        self.assertEqual(
            client.calls,
            [
                (
                    "upload_file",
                    {
                        "Filename": str(source),
                        "Bucket": "the-agent",
                        "Key": metadata.uri,
                        "ExtraArgs": {"ContentType": "video/mp4"},
                    },
                ),
            ],
        )

    def test_open_rejects_missing_body(self):
        client = FakeS3Client()
        client.omit_body = True
        storage = self.__storage(client)

        with self.assertRaisesRegex(ExternalServiceError, "returned no body"):
            storage.open(domain.chat_attachment())

    def test_storage_failures_preserve_cause(self):
        for operation, message in (
            ("head_bucket", "bucket check"),
            ("create_bucket", "bucket creation"),
            ("upload", "upload"),
            ("read", "read"),
            ("delete", "delete"),
        ):
            with self.subTest(operation = operation):
                client = FakeS3Client()
                storage = self.__storage(client)
                failure = external.s3_client_error()
                setattr(client, f"{operation}_error", failure)
                if operation == "create_bucket":
                    client.buckets.clear()
                metadata = domain.chat_attachment()
                with self.assertRaises(ExternalServiceError) as raised:
                    if operation in ("head_bucket", "create_bucket"):
                        storage.ensure_ready()
                    elif operation == "upload":
                        storage.put(metadata, b"content")
                    elif operation == "read":
                        storage.open(metadata)
                    else:
                        storage.delete(metadata)
                self.assertIn(message, str(raised.exception))
                self.assertIs(raised.exception.__cause__, failure)

    def __storage(self, client: FakeS3Client) -> S3AttachmentStorage:
        client.buckets.add(config.s3_bucket)
        interceptor = FakeInterceptor()
        interceptor.register(S3Client, client)
        di = self.enterContext(di_for_tests(interceptor = interceptor))
        return di.s3_attachment_storage()
