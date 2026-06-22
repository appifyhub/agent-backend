import urllib.parse
from uuid import UUID

import requests

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.supported_files import KNOWN_FILE_FORMATS
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util.config import config
from util.error_codes import UNSUPPORTED_MEDIA_TYPE
from util.errors import ValidationError
from util.functions import digest_md5


class UrlAttachmentResolver:

    __url: str
    __chat_id: UUID

    def __init__(self, url: str, di: DI):
        self.__url = url
        self.__chat_id = UUID(di.invoker_chat_id)

    def execute(self) -> ChatMessageAttachment:
        mime_type: str | None = self.__mime_from_head() or self.__mime_from_extension()
        if not mime_type:
            raise ValidationError(
                f"Cannot determine a supported media type for URL: {self.__url}",
                UNSUPPORTED_MEDIA_TYPE,
            )
        ext = self.__extension_for(mime_type)
        attachment_id = f"url-{digest_md5(self.__url)}"
        return ChatMessageAttachment(
            id = attachment_id,
            chat_id = self.__chat_id,
            message_id = f"virtual-{attachment_id}",
            last_url = self.__url,
            mime_type = mime_type,
            extension = ext,
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
                if candidate in KNOWN_FILE_FORMATS.values():
                    return candidate
        except Exception:
            pass
        return None

    def __mime_from_extension(self) -> str | None:
        path = urllib.parse.urlparse(self.__url).path
        if "." in path:
            ext = path.rsplit(".", 1)[-1].lower()
            return KNOWN_FILE_FORMATS.get(ext)
        return None

    def __extension_for(self, mime_type: str) -> str | None:
        path = urllib.parse.urlparse(self.__url).path
        if "." in path:
            ext = path.rsplit(".", 1)[-1].lower()
            if ext in KNOWN_FILE_FORMATS:
                return ext
        return next((k for k, v in KNOWN_FILE_FORMATS.items() if v == mime_type), None)
