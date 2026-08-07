import io
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, BinaryIO, cast

import requests
from pyuploadcare import Uploadcare

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.attachment_storage import AttachmentStorage, PublicAttachment
from util.config import config
from util.error_codes import ATTACHMENT_STORAGE_FAILED
from util.errors import ExternalServiceError

UPLOADCARE_PUBLIC_URL_TTL_SECONDS = 24 * 60 * 60


class _NamedUploadStream:

    name: str
    __stream: BinaryIO

    def __init__(self, stream: BinaryIO, name: str):
        self.__stream = stream
        self.name = name

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__stream, name)


class _ResponseStream(io.BufferedReader):

    __response: requests.Response

    def __init__(self, response: requests.Response):
        self.__response = response
        super().__init__(response.raw)

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.__response.close()


class UploadcareAttachmentStorage(AttachmentStorage):

    SERVES_PUBLIC_URLS = True

    __client: Uploadcare
    __cdn_base: str

    def __init__(self):
        self.__cdn_base = f"https://{config.uploadcare_cdn_id}.ucarecd.net/"
        self.__client = Uploadcare(
            public_key = config.uploadcare_public_key,
            secret_key = config.uploadcare_private_key.get_secret_value(),
            cdn_base = self.__cdn_base,
        )

    @classmethod
    def can_be_used(cls) -> bool:
        return bool(
            config.uploadcare_public_key and
            config.uploadcare_private_key.get_secret_value() and
            config.uploadcare_cdn_id,
        )

    def ensure_ready(self) -> None:
        pass

    def owns_uri(self, uri: str | None) -> bool:
        return bool(uri) and uri.startswith(self.__cdn_base)

    def put(self, metadata: ChatAttachment, content: bytes) -> str:
        with NamedTemporaryFile() as temp_file:
            temp_file.write(content)
            temp_file.flush()
            return self.put_file(metadata, Path(temp_file.name))

    def put_file(self, metadata: ChatAttachment, file_path: Path) -> str:
        try:
            filename = metadata.uri.rsplit("/", 1)[-1]
            with file_path.open("rb") as source:
                named_source = cast(BinaryIO, _NamedUploadStream(source, filename))
                stored_file = self.__client.upload(named_source, store = True)
            if not stored_file.cdn_url or not stored_file.filename:
                raise ExternalServiceError("Attachment storage upload returned no public URL", ATTACHMENT_STORAGE_FAILED)
            return f"{stored_file.cdn_url}{stored_file.filename}"
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Attachment storage upload failed", ATTACHMENT_STORAGE_FAILED) from e

    def open(self, metadata: ChatAttachment) -> BinaryIO:
        try:
            response = requests.get(metadata.last_url, timeout = config.web_timeout_s * 4, stream = True)
            if response.status_code != 200:
                response.close()
                raise ExternalServiceError("Attachment storage returned no body", ATTACHMENT_STORAGE_FAILED)
            response.raw.decode_content = True
            stream = _ResponseStream(response)
            try:
                has_content = bool(stream.peek(1))
            except Exception:
                stream.close()
                raise
            if not has_content:
                stream.close()
                raise ExternalServiceError("Attachment storage returned no body", ATTACHMENT_STORAGE_FAILED)
            return stream
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Attachment storage read failed", ATTACHMENT_STORAGE_FAILED) from e

    def delete(self, metadata: ChatAttachment) -> None:
        try:
            self.__client.file(metadata.last_url).delete()
        except Exception as e:
            raise ExternalServiceError("Attachment storage delete failed", ATTACHMENT_STORAGE_FAILED) from e

    def public_attachment_for(self, metadata: ChatAttachment) -> PublicAttachment:
        valid_until = datetime.now() + timedelta(seconds = UPLOADCARE_PUBLIC_URL_TTL_SECONDS)
        return PublicAttachment(
            id = metadata.id,
            url = metadata.last_url,
            valid_until = int(valid_until.timestamp()),
        )
