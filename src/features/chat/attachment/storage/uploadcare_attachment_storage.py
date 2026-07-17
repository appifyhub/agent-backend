import io
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
from typing import BinaryIO

import requests
from pyuploadcare import Uploadcare

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.attachment_storage import AttachmentStorage, PublicAttachment
from util.config import config
from util.error_codes import ATTACHMENT_STORAGE_FAILED
from util.errors import ExternalServiceError

UPLOADCARE_PUBLIC_URL_TTL_SECONDS = 24 * 60 * 60


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
        try:
            filename = metadata.uri.rsplit("/", 1)[-1]
            with NamedTemporaryFile(suffix = filename) as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                tmp_file.name = filename
                stored_file = self.__client.upload(tmp_file, store = True)
            if not stored_file.cdn_url or not stored_file.filename:
                raise ExternalServiceError("Attachment storage upload returned no public URL", ATTACHMENT_STORAGE_FAILED)
            return f"{stored_file.cdn_url}{stored_file.filename}"
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Attachment storage upload failed", ATTACHMENT_STORAGE_FAILED) from e

    def open(self, metadata: ChatAttachment) -> BinaryIO:
        try:
            response = requests.get(metadata.last_url, timeout = config.web_timeout_s * 4)
            if response.status_code != 200 or not response.content:
                raise ExternalServiceError("Attachment storage returned no body", ATTACHMENT_STORAGE_FAILED)
            return io.BytesIO(response.content)
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
