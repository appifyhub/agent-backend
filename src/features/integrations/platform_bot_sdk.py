from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import requests

from db.model.chat_config import ChatConfigDB
from db.schema.chat_message import ChatMessage
from db.schema.user import User
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.config.chat_config import ChatConfig
from features.images.image_size_utils import resize_file
from features.integrations.integration_config import TELEGRAM_MAX_PHOTO_SIZE_BYTES, WHATSAPP_MAX_PHOTO_SIZE_BYTES
from features.integrations.integrations import is_own_chat
from util import log
from util.error_codes import UNSUPPORTED_CHAT_TYPE
from util.errors import ConfigurationError
from util.functions import delete_file_safe


class ChatAccess(Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


class PlatformBotSDK:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def send_text_message(
        self,
        chat_id: int | str,
        text: str,
    ) -> ChatMessage:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_text_message(chat_id, text)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_text_message(chat_id, text)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
    ) -> ChatMessage:
        # Resize image if needed to fit platform limits
        resized_url = self.__resize_and_reupload(photo_url)
        # Send photo via platform-specific SDK
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_photo(chat_id, resized_url, caption)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_photo(chat_id, resized_url, caption)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def smart_send_photo(
        self,
        media_mode: ChatConfigDB.MediaMode,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
        thumbnail: str | None = None,
    ) -> ChatMessage:
        match media_mode:
            case ChatConfigDB.MediaMode.photo:
                try:
                    return self.send_photo(chat_id, photo_url, caption)
                except Exception as e:
                    log.e("Failed to send photo, falling back to document", e)
                    return self.send_document(chat_id, photo_url, caption, thumbnail = thumbnail)
            case ChatConfigDB.MediaMode.file:
                return self.send_document(chat_id, photo_url, caption, thumbnail = thumbnail)
            case ChatConfigDB.MediaMode.all:
                try:
                    self.send_photo(chat_id, photo_url, caption)
                except Exception as e:
                    log.e("Failed to send photo in 'all' mode, continuing with document", e)
                return self.send_document(chat_id, photo_url, caption, thumbnail = thumbnail)

    def send_document(
        self,
        chat_id: int | str,
        document_url: str,
        caption: str | None = None,
        thumbnail: str | None = None,
    ) -> ChatMessage:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_document(
                    chat_id = chat_id,
                    document_url = document_url,
                    thumbnail = thumbnail,
                    caption = caption,
                )
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_document(chat_id, document_url, caption)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def send_button_link(
        self,
        chat_id: int | str,
        link_url: str,
        button_text: str = "⚙️",
    ) -> ChatMessage:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_button_link(chat_id, link_url, button_text)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_button_link(chat_id, link_url, button_text)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def set_reaction(
        self,
        chat_id: int | str,
        message_id: int | str,
        reaction: str | None,
    ) -> None:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                self.__di.telegram_bot_sdk.set_reaction(chat_id, message_id, reaction)
            case ChatConfigDB.ChatType.whatsapp:
                self.__di.whatsapp_bot_sdk.set_reaction(chat_id, message_id, reaction)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def set_chat_action(
        self,
        chat_id: int | str,
        action: Literal["typing", "upload_photo"],
    ) -> None:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                self.__di.telegram_bot_sdk.set_chat_action(chat_id, action)
            case ChatConfigDB.ChatType.whatsapp:
                pass  # WhatsApp doesn't support chat actions (typing indicators)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def refresh_attachments_by_ids(
        self,
        attachment_ids: list[str],
    ) -> list[ChatMessageAttachment]:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.refresh_attachments_by_ids(attachment_ids)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.refresh_attachments_by_ids(attachment_ids)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def refresh_attachment_instances(
        self,
        attachments: list[ChatMessageAttachment],
    ) -> list[ChatMessageAttachment]:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.refresh_attachment_instances(attachments)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.refresh_attachment_instances(attachments)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def resolve_chat_access(self, chat: ChatConfig, user: User) -> ChatAccess | None:
        if is_own_chat(chat, user):
            return ChatAccess.owner
        if chat.is_private:
            return None
        match chat.chat_type:
            case ChatConfigDB.ChatType.telegram:
                if not user.telegram_user_id:
                    return None
                member = self.__di.telegram_bot_sdk.get_chat_member(str(chat.external_id), user.telegram_user_id)
                if member is None:
                    return None
                match member.status:
                    case "creator" | "administrator":
                        return ChatAccess.admin
                    case "member" | "restricted":
                        return ChatAccess.member
                    case _:
                        return None
            case _:
                return None

    def __resize_and_reupload(self, photo_url: str) -> str:
        chat_type = self.__di.require_invoker_chat_type()
        match chat_type:
            case ChatConfigDB.ChatType.whatsapp:
                max_size_bytes = WHATSAPP_MAX_PHOTO_SIZE_BYTES
            case ChatConfigDB.ChatType.telegram:
                max_size_bytes = TELEGRAM_MAX_PHOTO_SIZE_BYTES
            case _:
                log.t(f"No size limit for chat type {chat_type}, returning original URL")
                return photo_url

        size_mb = max_size_bytes / 1024 / 1024
        log.t(f"Checking if image needs resizing (max size: {size_mb:.2f} MB)")

        temp_path: str | None = None
        resized_path: str | None = None

        try:
            try:
                head_response = requests.head(photo_url, timeout = 10, allow_redirects = True)
                content_length = head_response.headers.get("Content-Length")

                if content_length:
                    file_size = int(content_length)
                    log.t(f"Image size from Content-Length: {file_size / 1024 / 1024:.2f} MB")
                    if file_size <= max_size_bytes:
                        log.t("Image is within size limit, no resizing needed")
                        return photo_url
            except Exception as e:
                log.w("Failed to get Content-Length, will download to check size", e)

            with NamedTemporaryFile(delete = False, suffix = Path(photo_url).suffix or ".img") as tmp:
                temp_path = tmp.name
                log.t(f"Downloading image to temp file: {temp_path}")
                with requests.get(photo_url, timeout = 30, stream = True) as response:
                    response.raise_for_status()
                    for chunk in response.iter_content(chunk_size = 1024 * 256):
                        if not chunk:
                            continue
                        tmp.write(chunk)

            downloaded_size = Path(temp_path).stat().st_size
            log.t(f"Downloaded image size: {downloaded_size / 1024 / 1024:.2f} MB")

            if downloaded_size <= max_size_bytes:
                log.t("Image is within size limit, no resizing needed")
                return photo_url

            log.i(f"Image exceeds size limit ({downloaded_size / 1024 / 1024:.2f} MB > {size_mb:.2f} MB), resizing...")
            resized_path = resize_file(temp_path, max_size_bytes)

            log.t(f"Resizing complete, uploading resized image from {resized_path}")
            uploader = self.__di.image_uploader(binary_image = Path(resized_path).read_bytes())
            return uploader.execute()

        except Exception as e:
            log.e("Failed to prepare image for upload, returning original URL", e)
            return photo_url
        finally:
            delete_file_safe(resized_path)
            delete_file_safe(temp_path)
