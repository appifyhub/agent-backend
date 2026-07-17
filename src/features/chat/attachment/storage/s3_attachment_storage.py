from typing import BinaryIO, cast

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.storage.attachment_storage import AttachmentStorage, PublicAttachment
from features.chat.attachment.storage.s3_client import S3Client
from features.chat.supported_files import resolve_file_type
from util.config import config
from util.error_codes import ATTACHMENT_STORAGE_FAILED, INVALID_ATTACHMENT_OPERATION
from util.errors import ExternalServiceError, InternalError

S3_ADDRESSING_STYLE = "path"


class S3AttachmentStorage(AttachmentStorage):

    SERVES_PUBLIC_URLS = False

    __bucket: str
    __client: S3Client

    def __init__(self):
        self.__bucket = config.s3_bucket
        self.__client = cast(S3Client, boto3.client(
            "s3",
            endpoint_url = config.s3_base_url,
            region_name = config.s3_region,
            aws_access_key_id = config.s3_access_key.get_secret_value(),
            aws_secret_access_key = config.s3_secret_key.get_secret_value(),
            config = BotoConfig(s3 = {"addressing_style": S3_ADDRESSING_STYLE}),
        ))

    @classmethod
    def can_be_used(cls) -> bool:
        return bool(
            config.s3_base_url and
            config.s3_access_key.get_secret_value() and
            config.s3_secret_key.get_secret_value() and
            config.s3_bucket and
            config.s3_region,
        )

    def ensure_ready(self) -> None:
        try:
            self.__client.head_bucket(Bucket = self.__bucket)
        except ClientError as e:
            if self.__is_missing_bucket_error(e):
                self.__create_bucket()
                return
            raise ExternalServiceError("Attachment storage bucket check failed", ATTACHMENT_STORAGE_FAILED) from e
        except Exception as e:
            raise ExternalServiceError("Attachment storage bucket check failed", ATTACHMENT_STORAGE_FAILED) from e

    def owns_uri(self, uri: str | None) -> bool:
        return bool(uri) and uri.startswith(f"s3://{self.__bucket}/")

    def put(self, metadata: ChatMessageAttachment, content: bytes) -> str:
        try:
            put_args: dict[str, object] = {"Bucket": self.__bucket, "Key": metadata.uri, "Body": content}
            mime_type, _ = resolve_file_type(mime_type = metadata.mime_type, extension = metadata.extension, uri = metadata.uri)
            if mime_type:
                put_args["ContentType"] = mime_type
            self.__client.put_object(**put_args)
            return f"s3://{self.__bucket}/{metadata.uri}"
        except Exception as e:
            raise ExternalServiceError("Attachment storage upload failed", ATTACHMENT_STORAGE_FAILED) from e

    def open(self, metadata: ChatMessageAttachment) -> BinaryIO:
        try:
            response = self.__client.get_object(Bucket = self.__bucket, Key = metadata.uri)
            body = response.get("Body")
            if body is None:
                raise ExternalServiceError("Attachment storage returned no body", ATTACHMENT_STORAGE_FAILED)
            return cast(BinaryIO, body)
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Attachment storage read failed", ATTACHMENT_STORAGE_FAILED) from e

    def delete(self, metadata: ChatMessageAttachment) -> None:
        try:
            self.__client.delete_object(Bucket = self.__bucket, Key = metadata.uri)
        except Exception as e:
            raise ExternalServiceError("Attachment storage delete failed", ATTACHMENT_STORAGE_FAILED) from e

    def public_attachment_for(self, _: ChatMessageAttachment) -> PublicAttachment:
        raise InternalError("S3 attachment storage does not serve public URLs", INVALID_ATTACHMENT_OPERATION)

    def __create_bucket(self) -> None:
        try:
            self.__client.create_bucket(Bucket = self.__bucket)
        except Exception as e:
            raise ExternalServiceError("Attachment storage bucket creation failed", ATTACHMENT_STORAGE_FAILED) from e

    def __is_missing_bucket_error(self, e: ClientError) -> bool:
        error = e.response.get("Error", {})
        response_metadata = e.response.get("ResponseMetadata", {})
        return (
            error.get("Code") in ["404", "NoSuchBucket", "NotFound"] or
            response_metadata.get("HTTPStatusCode") == 404
        )
