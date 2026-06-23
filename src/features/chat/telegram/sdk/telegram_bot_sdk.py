import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Literal

import requests

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.message.chat_message import ChatMessage
from features.chat.supported_files import KNOWN_FILE_FORMATS
from features.chat.telegram.model.attachment.file import File
from features.chat.telegram.model.chat_member import ChatMember
from features.chat.telegram.model.message import Message
from features.chat.telegram.model.update import Update
from util import log
from util.config import config
from util.error_codes import ATTACHMENT_NOT_FOUND, MISSING_EXTERNAL_ATTACHMENT_ID, PLATFORM_MAPPING_FAILED
from util.errors import InternalError, NotFoundError
from util.functions import detect_image_format, first_key_with_value


class TelegramBotSDK:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    # === API functions ===

    def send_text_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
        link_preview_options: dict | None = None,
    ) -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_text_message(
            chat_id = chat_id,
            text = text,
            parse_mode = parse_mode,
            disable_notification = disable_notification,
            link_preview_options = link_preview_options,
        )
        return self.__store_api_response_as_message(sent_message)

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_photo(
            chat_id = chat_id,
            photo_url = photo_url,
            caption = caption,
            parse_mode = parse_mode,
            disable_notification = disable_notification,
        )
        return self.__store_api_response_as_message(sent_message)

    def send_document(
        self,
        chat_id: int | str,
        document_url: str,
        parse_mode: str = "markdown",
        thumbnail: str | None = None,
        caption: str | None = None,
        disable_notification: bool = False,
    ) -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_document(
            chat_id = chat_id,
            document_url = document_url,
            caption = caption,
            parse_mode = parse_mode,
            thumbnail = thumbnail,
            disable_notification = disable_notification,
        )
        return self.__store_api_response_as_message(sent_message)

    def set_status_typing(self, chat_id: int | str):
        self.__di.telegram_bot_api.set_status_typing(chat_id)

    def set_status_uploading_image(self, chat_id: int | str):
        self.__di.telegram_bot_api.set_status_uploading_image(chat_id)

    def set_chat_action(self, chat_id: int | str, action: Literal["typing", "upload_photo"]):
        if action == "upload_photo":
            self.set_status_uploading_image(chat_id)
        else:
            self.set_status_typing(chat_id)

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None):
        self.__di.telegram_bot_api.set_reaction(chat_id = chat_id, message_id = message_id, reaction = reaction)

    def send_button_link(self, chat_id: int | str, link_url: str, button_text: str = "⚙️") -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_button_link(chat_id, link_url, button_text)
        return self.__store_api_response_as_message(sent_message)

    def get_chat_member(self, chat_id: int | str, user_id: int | str) -> ChatMember | None:
        try:
            return self.__di.telegram_bot_api.get_chat_member(chat_id, user_id)
        except Exception as e:
            log.e(f"Failed to get chat member '{user_id}' from chat '{chat_id}'", e)
            return None

    def get_chat_administrators(self, chat_id: int | str) -> list[ChatMember] | None:
        try:
            return self.__di.telegram_bot_api.get_chat_administrators(chat_id)
        except Exception as e:
            log.e(f"Failed to get chat administrators for chat '{chat_id}'", e)
            return None

    # === Data utilities ===

    def __store_api_response_as_message(self, raw_api_response: dict) -> ChatMessage:
        log.t("Storing API message data...")
        message = Message(**raw_api_response["result"])
        update = Update(update_id = time.time_ns(), message = message)
        mapping_result = self.__di.telegram_domain_mapper.map_update(update)
        if not mapping_result:
            raise InternalError(f"Telegram API domain mapping failed for local update '{update.update_id}'", PLATFORM_MAPPING_FAILED)  # noqa: E501
        resolution_result = self.__di.telegram_data_resolver.resolve(mapping_result)
        if not resolution_result.message:
            raise InternalError(f"Telegram data resolution failed for local update '{update.update_id}'", PLATFORM_MAPPING_FAILED)
        # noinspection PyTypeChecker
        return resolution_result.message

    def refresh_attachments_by_ids(self, attachment_ids: list[str]) -> list[ChatMessageAttachment]:
        log.d(f"Refreshing {len(attachment_ids)} attachments by IDs")
        attachments: list[ChatMessageAttachment] = []
        for attachment_id in attachment_ids:
            attachment = self.__di.chat_message_attachment_repo.get(attachment_id)
            if not attachment:
                raise NotFoundError(f"Attachment with ID '{attachment_id}' not found in DB", ATTACHMENT_NOT_FOUND)
            attachments.append(attachment)
        return self.refresh_attachment_instances(attachments)

    def refresh_attachment_instances(self, attachments: list[ChatMessageAttachment]) -> list[ChatMessageAttachment]:
        log.d(f"Refreshing {len(attachments)} attachment instances")
        return [self.refresh_attachment(attachment) for attachment in attachments]

    def refresh_attachment(self, attachment: ChatMessageAttachment) -> ChatMessageAttachment:
        log.d(f"Refreshing attachment '{attachment.id}'")

        # check if instance data is already fresh
        if not attachment.has_stale_data:
            log.t(f"Attachment '{attachment.id}': data is already fresh")
            # we store it anyway because it may contain fresh data from the API
            return self.__di.chat_message_attachment_repo.save(attachment)

        # data is stale or missing, we need to fetch the attachment data from remote
        if not attachment.external_id:
            raise InternalError("No external ID provided for the attachment", MISSING_EXTERNAL_ATTACHMENT_ID)
        log.t(f"Refreshing attachment data for external ID '{attachment.external_id}'")
        api_file: File = self.__di.telegram_bot_api.get_file_info(attachment.external_id)

        # let's populate the attachment with the data from the API
        updated_attachment = replace(attachment, size = api_file.file_size or attachment.size)
        if api_file.file_path:
            file_api_endpoint = f"{config.telegram_api_base_url}/file"
            bot_token = config.telegram_bot_token.get_secret_value()
            last_url = f"{file_api_endpoint}/bot{bot_token}/{api_file.file_path}"
            updated_attachment = replace(updated_attachment, last_url = last_url, last_url_until = self._nearest_hour_epoch())

        # let's set the additional available properties
        if not updated_attachment.extension:
            if api_file.file_path and "." in api_file.file_path:
                mime_type = updated_attachment.mime_type
                extension = api_file.file_path.lower().split(".")[-1] or updated_attachment.extension
                if not mime_type and extension:
                    mime_type = KNOWN_FILE_FORMATS.get(extension) or mime_type
                updated_attachment = replace(updated_attachment, extension = extension, mime_type = mime_type)
            elif updated_attachment.mime_type:
                extension = first_key_with_value(KNOWN_FILE_FORMATS, updated_attachment.mime_type) or updated_attachment.extension
                # reverse engineer the extension
                updated_attachment = replace(updated_attachment, extension = extension)
            elif updated_attachment.last_url:
                updated_attachment = self.__update_image_format(updated_attachment)

        # final version of the attachment is ready, store it
        return self.__di.chat_message_attachment_repo.save(updated_attachment)

    def __update_image_format(self, attachment: ChatMessageAttachment) -> ChatMessageAttachment:
        log.d("Both extension and mime_type are None, detecting from content")
        if not attachment.last_url:
            return attachment
        try:
            response = requests.get(attachment.last_url, timeout = 10)
            if response.status_code == 200:
                detected_format = detect_image_format(response.content)
                if detected_format and detected_format in KNOWN_FILE_FORMATS:
                    # detected format names match our KNOWN_FILE_FORMATS keys directly
                    mime_type = KNOWN_FILE_FORMATS[detected_format]
                    log.t(f"Detected format: {detected_format} -> {mime_type}")
                    return replace(attachment, extension = detected_format, mime_type = mime_type)
        except Exception as e:
            log.w("Failed to detect image format", e)
        return attachment

    @staticmethod
    def _nearest_hour_epoch() -> int:
        now = datetime.now()
        last_hour_mark: datetime = now.replace(minute = 0, second = 0, microsecond = 0)
        next_hour_mark: datetime = last_hour_mark + timedelta(hours = 1)
        log.t(f"Nearest hour at {now} is {next_hour_mark}")
        return int(next_hour_mark.timestamp())
