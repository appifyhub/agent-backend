from uuid import UUID

import requests

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.supported_files import is_supported_mime_type, resolve_file_type
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util.config import config
from util.error_codes import UNSUPPORTED_MEDIA_TYPE
from util.errors import ValidationError
from util.functions import digest_md5


class UrlAttachmentResolver:

    __url: str
    __chat_id: UUID
    __uploader_user_id: UUID

    def __init__(self, url: str, di: DI):
        self.__url = url
        self.__chat_id = UUID(di.invoker_chat_id)
        self.__uploader_user_id = di.invoker.id

    def execute(self) -> ChatMessageAttachment:
        mime_type, extension = resolve_file_type(mime_type = self.__mime_from_head(), uri = self.__url)
        if not mime_type:
            raise ValidationError(f"Cannot determine a supported media type for URL: {self.__url}", UNSUPPORTED_MEDIA_TYPE)
        attachment_id = f"url-{digest_md5(self.__url)}"
        return ChatMessageAttachment(
            id = attachment_id,
            chat_id = self.__chat_id,
            uploader_user_id = self.__uploader_user_id,
            message_id = f"virtual-{attachment_id}",
            last_url = self.__url,
            mime_type = mime_type,
            extension = extension,
        )

    def __mime_from_head(self) -> str | None:
        try:
            response = requests.head(
                self.__url,
                headers = DEFAULT_HEADERS,
                timeout = config.web_timeout_s,
                allow_redirects = True,
            )
            content_type = response.headers.get("Content-Type", "")
            if content_type:
                candidate = content_type.split(";")[0].strip()
                if is_supported_mime_type(candidate):
                    return candidate
        except Exception:
            pass
        return None
