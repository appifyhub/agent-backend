import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from botocore.exceptions import ClientError

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.s3_attachment_storage import S3_ADDRESSING_STYLE, S3AttachmentStorage
from features.chat.attachment.storage.s3_client import S3Client


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


class S3AttachmentStorageTest(unittest.TestCase):

    def test_declares_public_delivery_capability(self):
        self.assertFalse(S3AttachmentStorage.SERVES_PUBLIC_URLS)

    def test_can_be_used_requires_complete_config(self):
        with patch("features.chat.attachment.storage.s3_attachment_storage.config", self.__config()):
            self.assertTrue(S3AttachmentStorage.can_be_used())

        for missing_field in ["s3_base_url", "s3_region", "s3_bucket", "s3_access_key", "s3_secret_key"]:
            with self.subTest(missing_field = missing_field):
                with patch(
                    "features.chat.attachment.storage.s3_attachment_storage.config",
                    self.__config(missing_field = missing_field),
                ):
                    self.assertFalse(S3AttachmentStorage.can_be_used())

    def test_owns_uri_recognizes_own_bucket_locator(self):
        storage = self.__storage(FakeS3Client())
        metadata = self.__metadata()

        self.assertTrue(storage.owns_uri(f"s3://the-agent/{metadata.uri}"))
        self.assertFalse(storage.owns_uri("s3://other-bucket/chats/x"))
        self.assertFalse(storage.owns_uri("file:///tmp/chats/x"))
        self.assertFalse(storage.owns_uri(None))
        self.assertFalse(storage.owns_uri(""))

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

    def __config(self, missing_field: str | None = None, s3_base_url: str = "http://s3.local"):
        return SimpleNamespace(
            s3_base_url = "" if missing_field == "s3_base_url" else s3_base_url,
            s3_region = "" if missing_field == "s3_region" else "eu-central-1",
            s3_bucket = "" if missing_field == "s3_bucket" else "the-agent",
            s3_access_key = FakeSecret("" if missing_field == "s3_access_key" else "access"),
            s3_secret_key = FakeSecret("" if missing_field == "s3_secret_key" else "secret"),
        )

    def __metadata(
        self,
        mime_type: str | None = None,
        extension: str | None = None,
    ) -> ChatAttachment:
        return ChatAttachment(
            chat_id = UUID("11111111-1111-1111-1111-111111111111"),
            uploader_user_id = UUID(int = 9),
            message_id = "message-id",
            id = "attachment-id",
            mime_type = mime_type,
            extension = extension,
        )
