from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import requests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.images.image_bitmap_utils import add_outgoing_png_background
from features.images.image_size_utils import resize_file
from features.integrations.integration_config import TELEGRAM_MAX_PHOTO_SIZE_BYTES, WHATSAPP_MAX_PHOTO_SIZE_BYTES
from features.integrations.integrations import is_own_chat
from features.users.user import User
from util import log
from util.config import config
from util.error_codes import CHAT_CONFIG_NOT_FOUND, MEDIA_DOWNLOAD_FAILED, UNSUPPORTED_CHAT_TYPE
from util.errors import ConfigurationError, ExternalServiceError, NotFoundError
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
        chat_type = self.__di.require_invoker_chat_type()
        chat_config = self.__require_chat_config(chat_id, chat_type)

        match chat_type:
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_text_message(chat_config, text)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_text_message(chat_config, text)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {chat_type}", UNSUPPORTED_CHAT_TYPE)

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
    ) -> ChatMessage:
        chat_type = self.__di.require_invoker_chat_type()
        chat_config = self.__require_chat_config(chat_id, chat_type)
        attachment = self.prepare_outgoing_attachment(chat_config, photo_url, should_add_png_background = True)

        match chat_type:
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_photo(chat_config, attachment, caption)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_photo(chat_config, attachment, caption)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {chat_type}", UNSUPPORTED_CHAT_TYPE)

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
        chat_type = self.__di.require_invoker_chat_type()
        chat_config = self.__require_chat_config(chat_id, chat_type)

        attachment = self.prepare_outgoing_attachment(chat_config, document_url, should_resize = False)
        thumbnail_url: str | None = None
        if thumbnail:
            thumbnail_attachment = self.prepare_outgoing_attachment(chat_config, thumbnail)
            thumbnail_url = self.__di.chat_attachment_service.create_public_url(thumbnail_attachment).url

        match chat_type:
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_document(
                    chat_config = chat_config,
                    attachment = attachment,
                    thumbnail = thumbnail_url,
                    caption = caption,
                )
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_document(
                    chat_config = chat_config,
                    attachment = attachment,
                    caption = caption,
                )
            case _:
                raise ConfigurationError(f"Unsupported chat type: {chat_type}", UNSUPPORTED_CHAT_TYPE)

    def send_button_link(self, chat_id: int | str, link_url: str, button_text: str = "⚙️") -> ChatMessage:
        chat_type = self.__di.require_invoker_chat_type()
        chat_config = self.__require_chat_config(chat_id, chat_type)
        match chat_type:
            case ChatConfigDB.ChatType.telegram:
                return self.__di.telegram_bot_sdk.send_button_link(chat_config, link_url, button_text)
            case ChatConfigDB.ChatType.whatsapp:
                return self.__di.whatsapp_bot_sdk.send_button_link(chat_config, link_url, button_text)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {chat_type}", UNSUPPORTED_CHAT_TYPE)

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None) -> None:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                self.__di.telegram_bot_sdk.set_reaction(chat_id, message_id, reaction)
            case ChatConfigDB.ChatType.whatsapp:
                self.__di.whatsapp_bot_sdk.set_reaction(chat_id, message_id, reaction)
            case _:
                raise ConfigurationError(f"Unsupported chat type: {self.__di.require_invoker_chat_type()}", UNSUPPORTED_CHAT_TYPE)

    def set_chat_action(self, chat_id: int | str, action: Literal["typing", "upload_photo"]) -> None:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                self.__di.telegram_bot_sdk.set_chat_action(chat_id, action)
            case ChatConfigDB.ChatType.whatsapp:
                pass  # WhatsApp doesn't support chat actions (typing indicators)
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

    def prepare_outgoing_attachment(
        self,
        chat_config: ChatConfig,
        public_url: str,
        should_resize: bool = True,
        should_add_png_background: bool = False,
    ) -> ChatAttachment:
        # first, we find the max size for photos
        max_size_bytes: int | None = None
        if should_resize:
            chat_type = self.__di.require_invoker_chat_type()
            match chat_type:
                case ChatConfigDB.ChatType.telegram:
                    max_size_bytes = TELEGRAM_MAX_PHOTO_SIZE_BYTES
                case ChatConfigDB.ChatType.whatsapp:
                    max_size_bytes = WHATSAPP_MAX_PHOTO_SIZE_BYTES
                case _:
                    raise ConfigurationError(f"Unsupported chat type: {chat_type}", UNSUPPORTED_CHAT_TYPE)

        # next, we download the file to a temp location for resizing
        temp_path: str | None = None
        prepared_path: str | None = None
        resized_path: str | None = None
        try:
            with NamedTemporaryFile(delete = False) as tmp:
                temp_path = tmp.name
                log.t(f"Downloading outbound media to temp file: {temp_path}")
                try:
                    with requests.get(public_url, timeout = config.web_timeout_s * 3, stream = True) as response:
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size = 1024 * 256):
                            tmp.write(chunk)
                except Exception as e:
                    log.w(f"Could not download outbound media '{public_url[:4]}...{public_url[-4:]}'", e)
                    raise ExternalServiceError("Could not download outbound media", MEDIA_DOWNLOAD_FAILED) from e
            if Path(temp_path).stat().st_size == 0:
                log.w(f"Downloaded outbound media is empty '{public_url[:4]}...{public_url[-4:]}'")
                raise ExternalServiceError("Could not download outbound media", MEDIA_DOWNLOAD_FAILED)

            prepared_path = add_outgoing_png_background(temp_path) if should_add_png_background else temp_path
            resized_path = resize_file(prepared_path, max_size_bytes)
            attachment = self.__di.chat_attachment_service.save(
                attachment = ChatAttachment(chat_id = chat_config.chat_id, uploader_user_id = self.__di.invoker.id),
                content = Path(resized_path).read_bytes(),
            )
            log.t(f"Prepared outgoing attachment '{attachment.id}'")
            return attachment
        finally:
            delete_file_safe(temp_path)
            delete_file_safe(prepared_path)
            delete_file_safe(resized_path)

    def __require_chat_config(self, chat_id: int | str, chat_type: ChatConfigDB.ChatType) -> ChatConfig:
        chat_config = self.__di.chat_config_repo.get_by_external_identifiers(str(chat_id), chat_type)
        if not chat_config:
            raise NotFoundError(f"Chat config not found for chat: {chat_id}", CHAT_CONFIG_NOT_FOUND)
        return chat_config
