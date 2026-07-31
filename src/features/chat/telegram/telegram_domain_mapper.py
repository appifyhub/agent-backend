from datetime import datetime

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.telegram.model.message import Message as TelegramMessage
from features.users.user_remote_data import UserRemoteData
from util import log


class TelegramDomainMapper:

    def map_message(self, message: TelegramMessage) -> ChatMessageRemoteData:
        log.t(f"  Mapping message: {message}")
        text = "\n\n".join(part for part in [message.caption, message.text] if part)
        return ChatMessageRemoteData(
            message_id = str(message.message_id),
            sent_at = datetime.fromtimestamp(message.edit_date or message.date),
            text = text,
            replied_to_message_id = (
                str(message.reply_to_message.message_id)
                if message.reply_to_message
                else None
            ),
            quote_text = message.quote.text if message.quote else None,
        )

    # noinspection PyMethodMayBeStatic
    def map_author(self, message: TelegramMessage) -> UserRemoteData | None:
        if not message.from_user:
            return None
        log.t(f"  Mapping author {message.from_user}")
        # properties might be updated later when this is stored
        author = message.from_user
        telegram_chat_id = (
            str(message.chat.id)
            if message.chat.type == "private" and message.chat.id == author.id
            else None
        )
        return UserRemoteData(
            full_name = f"{author.first_name} {author.last_name}" if author.last_name else author.first_name,
            telegram_username = author.username,
            telegram_chat_id = telegram_chat_id,
            telegram_user_id = author.id,
        )

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
            attachments.append(
                self.__map_attachment(
                    file_id = message.audio.file_id,
                    file_size = message.audio.file_size,
                    message_id = str(message.message_id),
                    mime_type = message.audio.mime_type,
                ),
            )
        if message.document:
            log.t(f"  Mapping document: {message.document}")
            attachments.append(
                self.__map_attachment(
                    file_id = message.document.file_id,
                    file_size = message.document.file_size,
                    message_id = str(message.message_id),
                    mime_type = message.document.mime_type,
                ),
            )
        if message.photo:
            largest_photo = max(message.photo, key = lambda size: size.width * size.height)
            log.t(f"  Mapping photo: {largest_photo}")
            attachments.append(
                self.__map_attachment(
                    file_id = largest_photo.file_id,
                    file_size = largest_photo.file_size,
                    message_id = str(message.message_id),
                    mime_type = None,
                ),
            )
        if message.video:
            log.t(f"  Mapping video: {message.video}")
            attachments.append(
                self.__map_attachment(
                    file_id = message.video.file_id,
                    file_size = message.video.file_size,
                    message_id = str(message.message_id),
                    mime_type = message.video.mime_type,
                ),
            )
        if message.voice:
            log.t(f"  Mapping voice: {message.voice}")
            attachments.append(
                self.__map_attachment(
                    file_id = message.voice.file_id,
                    file_size = message.voice.file_size,
                    message_id = str(message.message_id),
                    mime_type = message.voice.mime_type,
                ),
            )
        return attachments

    # noinspection PyMethodMayBeStatic
    def __map_attachment(
        self,
        file_id: str,
        file_size: int | None,
        message_id: str,
        mime_type: str | None,
    ) -> ChatAttachmentRemoteData:
        log.t(f"    Creating attachment from file ID: {file_id}")
        return ChatAttachmentRemoteData(
            external_id = file_id,
            message_id = message_id,
            size = file_size,
            mime_type = mime_type,
        )
