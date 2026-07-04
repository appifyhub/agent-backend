import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from botocore.exceptions import ClientError

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.storage.local_attachment_storage import LocalAttachmentStorage
from features.chat.attachment.storage.s3_attachment_storage import S3_ADDRESSING_STYLE, S3AttachmentStorage
from features.chat.attachment.storage.s3_client import S3Client
from util.errors import ValidationError


class FakeS3Client(S3Client):

    calls: list[tuple[str, dict[str, object]]]
    head_bucket_error: Exception | None
    get_object_response: dict[str, object] | None

    def __init__(self):
        self.calls = []
        self.head_bucket_error = None
        self.get_object_response = None

    def head_bucket(self, Bucket: str) -> object:
        self.calls.append(("head_bucket", {"Bucket": Bucket}))
        if self.head_bucket_error is not None:
            raise self.head_bucket_error
        return None

    def create_bucket(self, Bucket: str) -> object:
        self.calls.append(("create_bucket", {"Bucket": Bucket}))
        return None

    def put_object(self, **kwargs: object) -> object:
        self.calls.append(("put_object", dict(kwargs)))
        return None

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        self.calls.append(("get_object", {"Bucket": Bucket, "Key": Key}))
        return self.get_object_response or {}

    def delete_object(self, Bucket: str, Key: str) -> object:
        self.calls.append(("delete_object", {"Bucket": Bucket, "Key": Key}))
        return None


class FakeSecret:

    __value: str

    def __init__(self, value: str):
        self.__value = value

    def get_secret_value(self) -> str:
        return self.__value


class LocalAttachmentStorageTest(unittest.TestCase):

    def test_put_open_and_delete_uses_local_storage_root(self):
        metadata = self.__metadata()
        content = b"stored content"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storage = LocalAttachmentStorage(root)

            storage.ensure_ready()
            storage.put(metadata, content)

            with storage.open(metadata) as stream:
                self.assertEqual(stream.read(), content)

            expected_path = root.joinpath(*metadata.uri.split("/"))
            self.assertTrue(expected_path.exists())

            storage.delete(metadata)
            storage.delete(metadata)

            self.assertFalse(expected_path.exists())

    def test_rejects_path_traversal_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalAttachmentStorage(Path(temp_dir))
            metadata = self.__metadata(attachment_id = "../outside")

            with self.assertRaises(ValidationError):
                storage.put(metadata, b"content")

    def __metadata(self, attachment_id: str = "attachment-id") -> ChatMessageAttachment:
        return ChatMessageAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            message_id = "message-id",
            id = attachment_id,
            mime_type = "text/plain",
            extension = "txt",
        )


class S3AttachmentStorageTest(unittest.TestCase):

    def test_configures_boto3_client_for_path_style_endpoint(self):
        with patch("features.chat.attachment.storage.s3_attachment_storage.config", self.__config(
            s3_base_url = "http://seaweedfs-s3.storage.svc.cluster.local:8333",
        )):
            with patch("features.chat.attachment.storage.s3_attachment_storage.boto3.client") as boto_client:
                S3AttachmentStorage()

                boto_client.assert_called_once()
                args = boto_client.call_args.args
                kwargs = boto_client.call_args.kwargs
                self.assertEqual(args, ("s3",))
                self.assertEqual(kwargs["endpoint_url"], "http://seaweedfs-s3.storage.svc.cluster.local:8333")
                self.assertEqual(kwargs["region_name"], "eu-central-1")
                self.assertEqual(kwargs["aws_access_key_id"], "access")
                self.assertEqual(kwargs["aws_secret_access_key"], "secret")
                self.assertEqual(kwargs["config"].s3["addressing_style"], S3_ADDRESSING_STYLE)

    def test_ensure_ready_accepts_existing_bucket(self):
        client = FakeS3Client()
        storage = self.__storage(client)

        storage.ensure_ready()

        self.assertEqual(client.calls, [("head_bucket", {"Bucket": "the-agent"})])

    def test_ensure_ready_creates_missing_bucket(self):
        client = FakeS3Client()
        client.head_bucket_error = ClientError(
            {
                "Error": {"Code": "NoSuchBucket"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "HeadBucket",
        )
        storage = self.__storage(client)

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
        client.get_object_response = {"Body": io.BytesIO(b"stored content")}
        storage = self.__storage(client)
        metadata = self.__metadata(mime_type = "text/plain")

        storage.put(metadata, b"stored content")
        stream = storage.open(metadata)
        storage.delete(metadata)

        self.assertEqual(stream.read(), b"stored content")
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

    def test_put_derives_content_type_from_extension(self):
        client = FakeS3Client()
        storage = self.__storage(client)
        metadata = self.__metadata(extension = "png")

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
                        "ContentType": "image/png",
                    },
                ),
            ],
        )

    def __storage(self, client: FakeS3Client) -> S3AttachmentStorage:
        with patch("features.chat.attachment.storage.s3_attachment_storage.config", self.__config()):
            with patch("features.chat.attachment.storage.s3_attachment_storage.boto3.client", return_value = client):
                return S3AttachmentStorage()

    def __config(self, s3_base_url: str = "http://s3.local"):
        return SimpleNamespace(
            s3_base_url = s3_base_url,
            s3_region = "eu-central-1",
            s3_bucket = "the-agent",
            s3_access_key = FakeSecret("access"),
            s3_secret_key = FakeSecret("secret"),
        )

    def __metadata(
        self,
        mime_type: str | None = None,
        extension: str | None = None,
    ) -> ChatMessageAttachment:
        return ChatMessageAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            message_id = "message-id",
            id = "attachment-id",
            mime_type = mime_type,
            extension = extension,
        )


class DIAttachmentStorageTest(unittest.TestCase):

    def test_uses_local_storage_when_s3_base_url_is_empty(self):
        with patch("di.di.config", self.__config(s3_base_url = "")):
            with patch("features.chat.attachment.storage.local_attachment_storage.LocalAttachmentStorage") as storage_class:
                storage = Mock()
                storage_class.return_value = storage

                result = DI().attachment_storage

                self.assertIs(result, storage)
                storage_class.assert_called_once_with()
                storage.ensure_ready.assert_called_once_with()

    def test_uses_s3_storage_when_s3_base_url_is_set(self):
        with patch("di.di.config", self.__config(s3_base_url = "http://s3.local")):
            with patch("features.chat.attachment.storage.s3_attachment_storage.S3AttachmentStorage") as storage_class:
                storage = Mock()
                storage_class.return_value = storage

                result = DI().attachment_storage

                self.assertIs(result, storage)
                storage_class.assert_called_once_with()
                storage.ensure_ready.assert_called_once_with()

    def __config(self, s3_base_url: str):
        return SimpleNamespace(
            s3_base_url = s3_base_url,
            s3_region = "eu-central-1",
            s3_bucket = "the-agent",
            s3_access_key = FakeSecret("access"),
            s3_secret_key = FakeSecret("secret"),
        )
