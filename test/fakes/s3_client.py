from io import BytesIO
from pathlib import Path
from typing import cast

from stubs import external

from features.chat.attachment.storage.s3_client import S3Client


class FakeS3Client(S3Client):

    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.head_bucket_error: Exception | None = None
        self.create_bucket_error: Exception | None = None
        self.upload_error: Exception | None = None
        self.read_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.omit_body = False

    def head_bucket(self, Bucket: str) -> object:
        self.calls.append(("head_bucket", {"Bucket": Bucket}))
        if self.head_bucket_error is not None:
            raise self.head_bucket_error
        if Bucket not in self.buckets:
            raise external.s3_client_error(code = "NoSuchBucket", status = 404, operation = "HeadBucket")
        return None

    def create_bucket(self, Bucket: str) -> object:
        self.calls.append(("create_bucket", {"Bucket": Bucket}))
        if self.create_bucket_error is not None:
            raise self.create_bucket_error
        self.buckets.add(Bucket)
        return None

    def put_object(self, **kwargs: object) -> object:
        self.calls.append(("put_object", dict(kwargs)))
        self.__store(str(kwargs["Bucket"]), str(kwargs["Key"]), cast(bytes, kwargs["Body"]))
        return None

    def upload_file(self, **kwargs: object) -> object:
        self.calls.append(("upload_file", dict(kwargs)))
        self.__store(str(kwargs["Bucket"]), str(kwargs["Key"]), Path(str(kwargs["Filename"])).read_bytes())
        return None

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        self.calls.append(("get_object", {"Bucket": Bucket, "Key": Key}))
        if self.read_error is not None:
            raise self.read_error
        if self.omit_body:
            return {}
        if (Bucket, Key) not in self.objects:
            raise external.s3_client_error(code = "NoSuchKey", status = 404, operation = "GetObject")
        return external.s3_object_response(body = BytesIO(self.objects[Bucket, Key]))

    def delete_object(self, Bucket: str, Key: str) -> object:
        self.calls.append(("delete_object", {"Bucket": Bucket, "Key": Key}))
        if self.delete_error is not None:
            raise self.delete_error
        self.objects.pop((Bucket, Key), None)
        return None

    def __store(self, bucket: str, key: str, content: bytes) -> None:
        if self.upload_error is not None:
            raise self.upload_error
        if bucket not in self.buckets:
            raise external.s3_client_error(code = "NoSuchBucket", status = 404, operation = "PutObject")
        self.objects[bucket, key] = content
