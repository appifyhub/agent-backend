import time
from dataclasses import replace
from typing import Literal

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.message.chat_message import ChatMessage
from features.chat.telegram.model.chat_member import ChatMember
from features.chat.telegram.model.message import Message
from features.chat.telegram.model.update import Update
from util import log
from util.error_codes import PLATFORM_MAPPING_FAILED
from util.errors import InternalError


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
        attachment: ChatMessageAttachment,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> ChatMessage:
        # the attachment is already archived; expose it via a public URL for delivery
        public_url = self.__di.chat_message_attachment_service.create_public_url(attachment).url
        # sending will generate a real message ID
        sent_message = self.__di.telegram_bot_api.send_photo(
            chat_id = chat_id,
            photo_url = public_url,
            caption = caption,
            parse_mode = parse_mode,
            disable_notification = disable_notification,
        )
        message = self.__store_api_response_as_message(sent_message)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_message_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def send_document(
        self,
        chat_id: int | str,
        attachment: ChatMessageAttachment,
        parse_mode: str = "markdown",
        thumbnail: str | None = None,
        caption: str | None = None,
        disable_notification: bool = False,
    ) -> ChatMessage:
        # the attachment is already archived; expose it via a public URL for delivery
        public_url = self.__di.chat_message_attachment_service.create_public_url(attachment).url
        # sending will generate a real message ID
        sent_message = self.__di.telegram_bot_api.send_document(
            chat_id = chat_id,
            document_url = public_url,
            caption = caption,
            parse_mode = parse_mode,
            thumbnail = thumbnail,
            disable_notification = disable_notification,
        )
        message = self.__store_api_response_as_message(sent_message)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_message_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

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
