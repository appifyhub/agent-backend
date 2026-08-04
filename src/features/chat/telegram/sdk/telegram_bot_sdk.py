from dataclasses import replace
from datetime import datetime
from typing import Literal

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.formatted_chat_message import (
    FormattedAttachmentPart,
    FormattedChatMessage,
    FormattedChatMessagePart,
    FormattedTextPart,
)
from features.chat.supported_files import KNOWN_VIDEO_FORMATS
from features.chat.telegram.model.chat_member import ChatMember
from features.chat.telegram.model.message import Message
from features.integrations.integration_config import THE_AGENT
from features.videos.video_file_utils import inspect_video
from util import log
from util.functions import obfuscate_url


class TelegramBotSDK:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    # === API functions ===

    def send_text_message(
        self,
        chat_config: ChatConfig,
        text: str,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
        link_preview_options: dict | None = None,
    ) -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_text_message(
            chat_id = chat_config.external_id,
            text = text,
            parse_mode = parse_mode,
            disable_notification = disable_notification,
            link_preview_options = link_preview_options,
        )
        return self.__store_api_response_as_message(sent_message, text = text, chat_config = chat_config)

    def send_photo(
        self,
        chat_config: ChatConfig,
        attachment: ChatAttachment,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> ChatMessage:
        # the attachment is already archived; expose it via a public URL for delivery
        public_url = self.__di.chat_attachment_service.create_public_url(attachment).url
        # sending will generate a real message ID
        sent_message = self.__di.telegram_bot_api.send_photo(
            chat_id = chat_config.external_id,
            photo_url = public_url,
            caption = caption,
            parse_mode = parse_mode,
            disable_notification = disable_notification,
        )
        content = self.__format_media_message(attachment, caption)
        message = self.__store_api_response_as_message(sent_message, text = content.to_text(), chat_config = chat_config)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def send_document(
        self,
        chat_config: ChatConfig,
        attachment: ChatAttachment,
        parse_mode: str = "markdown",
        thumbnail: str | None = None,
        caption: str | None = None,
        disable_notification: bool = False,
    ) -> ChatMessage:
        if attachment.mime_type in KNOWN_VIDEO_FORMATS.values():
            # video must go in a special way, so temporary path is yielded as a context for the file upload
            with self.__di.attachment_storage.temporary_path(attachment) as document_path:
                # sending will generate a real message ID
                sent_message = self.__di.telegram_bot_api.send_document(
                    chat_id = chat_config.external_id,
                    document_path = document_path,
                    filename = f"{attachment.id}.{attachment.extension}" if attachment.extension else None,
                    caption = caption,
                    parse_mode = parse_mode,
                    thumbnail = thumbnail,
                    disable_notification = disable_notification,
                )
        else:
            # sending will generate a real message ID
            public_url = self.__di.chat_attachment_service.create_public_url(attachment).url
            sent_message = self.__di.telegram_bot_api.send_document(
                chat_id = chat_config.external_id,
                document_url = public_url,
                caption = caption,
                parse_mode = parse_mode,
                thumbnail = thumbnail,
                disable_notification = disable_notification,
            )
        content = self.__format_media_message(attachment, caption)
        message = self.__store_api_response_as_message(sent_message, text = content.to_text(), chat_config = chat_config)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def send_video(
        self,
        chat_config: ChatConfig,
        attachment: ChatAttachment,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> ChatMessage:
        # temporary path is yielded as a context for the file upload
        with self.__di.attachment_storage.temporary_path(attachment) as video_path:
            sent_message = self.__di.telegram_bot_api.send_video(
                chat_id = chat_config.external_id,
                video_path = video_path,
                metadata = inspect_video(video_path),
                caption = caption,
                parse_mode = parse_mode,
                disable_notification = disable_notification,
            )
        content = self.__format_media_message(attachment, caption)
        message = self.__store_api_response_as_message(sent_message, text = content.to_text(), chat_config = chat_config)
        self.__di.chat_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def set_status_typing(self, chat_id: int | str):
        self.__di.telegram_bot_api.set_status_typing(chat_id)

    def set_status_uploading_image(self, chat_id: int | str):
        self.__di.telegram_bot_api.set_status_uploading_image(chat_id)

    def set_status_uploading_video(self, chat_id: int | str):
        self.__di.telegram_bot_api.set_status_uploading_video(chat_id)

    def set_chat_action(self, chat_id: int | str, action: Literal["typing", "upload_photo", "upload_video"]):
        if action == "upload_photo":
            self.set_status_uploading_image(chat_id)
        elif action == "upload_video":
            self.set_status_uploading_video(chat_id)
        else:
            self.set_status_typing(chat_id)

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None):
        self.__di.telegram_bot_api.set_reaction(chat_id = chat_id, message_id = message_id, reaction = reaction)

    def send_button_link(self, chat_config: ChatConfig, link_url: str, button_text: str = "⚙️") -> ChatMessage:
        sent_message = self.__di.telegram_bot_api.send_button_link(chat_config.external_id, link_url, button_text)
        stored_text = f"{button_text} {obfuscate_url(link_url)}"
        return self.__store_api_response_as_message(sent_message, text = stored_text, chat_config = chat_config)

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

    def __store_api_response_as_message(self, raw_api_response: dict, text: str, chat_config: ChatConfig) -> ChatMessage:
        log.t("Storing API message data...")
        api_message = Message(**raw_api_response["result"])
        message = ChatMessage(
            message_id = str(api_message.message_id),
            chat_id = chat_config.chat_id,
            author_id = THE_AGENT.id,
            sent_at = datetime.fromtimestamp(api_message.date),
            text = text,
        )
        return self.__di.chat_message_repo.save(message)

    # noinspection PyMethodMayBeStatic
    def __format_media_message(self, attachment: ChatAttachment, caption: str | None) -> FormattedChatMessage:
        parts: list[FormattedChatMessagePart] = []
        if caption:
            parts.append(FormattedTextPart(text = caption))
        parts.append(FormattedAttachmentPart.from_attachments([attachment]))
        return FormattedChatMessage(parts = parts)
