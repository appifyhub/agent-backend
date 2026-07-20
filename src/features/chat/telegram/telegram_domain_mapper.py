from dataclasses import dataclass
from datetime import datetime

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.message.formatted_chat_message import (
    FormattedAttachmentPart,
    FormattedChatMessage,
    FormattedQuotePart,
    FormattedTextPart,
)
from features.chat.telegram.model.attachment.file import File
from features.chat.telegram.model.message import Message as TelegramMessage
from features.chat.telegram.model.update import Update
from features.users.user_remote_data import UserRemoteData
from util import log
from util.config import config


class TelegramDomainMapper:

    @dataclass(kw_only = True)
    class Result:

        chat: ChatConfigRemoteData
        author: UserRemoteData | None
        message: ChatMessageRemoteData
        formatted_message: FormattedChatMessage | None = None
        attachments: list[ChatAttachmentRemoteData]
        replied_to_message_id: str | None = None

    def map_update(self, update: Update) -> Result | None:
        log.t(f"Mapping Telegram update: {update}")
        message = update.edited_message or update.message
        if not message:
            log.w(f"  Nothing to map in update: {update}")
            return None
        result_chat = self.map_chat(message)
        result_author = self.map_author(message)
        result_attachments = self.map_attachments(message)
        result_formatted_message = self.map_content(message, result_attachments)
        result_message = self.map_message(message, result_formatted_message)
        replied_to_message_id = str(message.reply_to_message.message_id) if message.reply_to_message else None
        return TelegramDomainMapper.Result(
            chat = result_chat,
            author = result_author,
            message = result_message,
            formatted_message = result_formatted_message,
            attachments = result_attachments,
            replied_to_message_id = replied_to_message_id,
        )

    def map_message(self,
        message: TelegramMessage,
        formatted_message: FormattedChatMessage | None = None,
    ) -> ChatMessageRemoteData:
        log.t(f"  Mapping message: {message}")
        formatted_message = formatted_message or self.map_content(message)
        return ChatMessageRemoteData(
            message_id = str(message.message_id),
            sent_at = datetime.fromtimestamp(message.edit_date or message.date),
            text = formatted_message.to_text(),
        )

    # noinspection PyMethodMayBeStatic
    def map_author(self, message: TelegramMessage) -> UserRemoteData | None:
        if not message.from_user:
            return None
        log.t(f"  Mapping author {message.from_user}")
        # properties might be updated later when this is stored
        author = message.from_user
        return UserRemoteData(
            full_name = f"{author.first_name} {author.last_name}" if author.last_name else author.first_name,
            telegram_username = author.username,
            telegram_chat_id = str(message.chat.id) if message.chat.type == "private" else None,
            telegram_user_id = author.id,
        )

    def map_content(
        self,
        message: TelegramMessage,
        attachments: list[ChatAttachmentRemoteData] | None = None,
    ) -> FormattedChatMessage:
        parts = []
        quote = message.quote.text if message.quote else None
        if quote:
            parts.append(
                FormattedQuotePart(message = FormattedChatMessage(parts = [
                    FormattedTextPart(text = quote),
                ])),
            )
        if message.caption:
            parts.append(FormattedTextPart(text = message.caption))
        if message.text:
            parts.append(FormattedTextPart(text = message.text))
        attachments = attachments if attachments is not None else self.map_attachments(message)
        if attachments:
            parts.append(FormattedAttachmentPart.from_remote_data(attachments))
        log.t(f"  Mapping message text: {parts}")
        return FormattedChatMessage(parts = parts)

    def map_chat(self, message: TelegramMessage) -> ChatConfigRemoteData:
        chat = message.chat
        log.t(f"  Mapping chat: {chat}")
        title = self.resolve_chat_name(str(chat.id), chat.title, chat.username, chat.first_name, chat.last_name)
        language_code = message.from_user.language_code if message.from_user else None
        return ChatConfigRemoteData(
            external_id = str(chat.id),
            title = title,
            is_private = chat.type == "private",
            language_iso_code = language_code,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

    # noinspection PyMethodMayBeStatic
    def resolve_chat_name(
        self,
        chat_id: str,
        title: str | None,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> str:
        parts = []
        if title:
            parts.append(title)
        if first_name or last_name:
            owner_parts = []
            if first_name:
                owner_parts.append(first_name)
            if last_name:
                owner_parts.append(last_name)
            parts.append(" ".join(owner_parts))
        if username:
            parts.append(f"@{username}")
        result = " · ".join(parts) if parts else f"#{chat_id}"
        log.t(f"  Resolved chat name {result}")
        return result

    def map_attachments(self, message: TelegramMessage) -> list[ChatAttachmentRemoteData]:
        attachments: list[ChatAttachmentRemoteData] = []
        if message.audio:
            log.t(f"  Mapping audio: {message.audio}")
            dummy_file = File(
                file_id = message.audio.file_id,
                file_unique_id = message.audio.file_unique_id,
                file_size = message.audio.file_size,
            )
            attachments.append(
                self.map_to_attachment(
                    file = dummy_file,
                    message_id = str(message.message_id),
                    mime_type = message.audio.mime_type,
                ),
            )
        if message.document:
            log.t(f"  Mapping document: {message.document}")
            dummy_file = File(
                file_id = message.document.file_id,
                file_unique_id = message.document.file_unique_id,
                file_size = message.document.file_size,
            )
            attachments.append(
                self.map_to_attachment(
                    file = dummy_file,
                    message_id = str(message.message_id),
                    mime_type = message.document.mime_type,
                ),
            )
        if message.photo:
            largest_photo = max(message.photo, key = lambda size: size.width * size.height)
            log.t(f"  Mapping photo: {largest_photo}")
            dummy_file = File(
                file_id = largest_photo.file_id,
                file_unique_id = largest_photo.file_unique_id,
                file_size = largest_photo.file_size,
            )
            attachments.append(
                self.map_to_attachment(
                    file = dummy_file,
                    message_id = str(message.message_id),
                    mime_type = None,
                ),
            )
        if message.voice:
            log.t(f"  Mapping voice: {message.voice}")
            dummy_file = File(
                file_id = message.voice.file_id,
                file_unique_id = message.voice.file_unique_id,
                file_size = message.voice.file_size,
            )
            attachments.append(
                self.map_to_attachment(
                    file = dummy_file,
                    message_id = str(message.message_id),
                    mime_type = message.voice.mime_type,
                ),
            )
        return attachments

    # noinspection PyMethodMayBeStatic
    def map_to_attachment(
        self,
        file: File,
        message_id: str,
        mime_type: str | None,
    ) -> ChatAttachmentRemoteData:
        log.t(f"    Creating attachment from file: {file}")
        bot_token = config.telegram_bot_token.get_secret_value()
        last_url = f"{config.telegram_api_base_url}/file/bot{bot_token}/{file.file_path}"
        return ChatAttachmentRemoteData(
            external_id = file.file_id,
            message_id = message_id,
            size = file.file_size,
            last_url = last_url if file.file_path else None,
            mime_type = mime_type,
        )
