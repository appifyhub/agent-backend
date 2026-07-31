from dataclasses import replace
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_mapper import from_remote_data as from_remote_data_attachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_mapper import apply_remote_data as apply_remote_data_message
from features.chat.message.chat_message_mapper import from_remote_data as from_remote_data_message
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.message.formatted_chat_message import FormattedChatMessage
from features.chat.telegram.model.message import Message as TelegramMessage
from features.chat.telegram.model.update import Update
from features.integrations.integrations import is_the_agent
from features.users.user import User
from features.users.user_mapper import apply_remote_data as apply_remote_data_user
from features.users.user_mapper import from_remote_data as from_remote_data_user
from features.users.user_remote_data import UserRemoteData
from util import log
from util.config import config
from util.error_codes import MEDIA_DOWNLOAD_FAILED, PLATFORM_MAPPING_FAILED
from util.errors import ExternalServiceError, InternalError


class TelegramChatInboundService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def ingest_update(self, update: Update) -> IngestedChatMessage | None:
        log.t(f"Ingesting Telegram update: {update}")
        message = update.edited_message or update.message
        if not message:
            log.w(f"  Nothing to ingest in update: {update}")
            return None
        return self.ingest_message(message)

    def ingest_message(self, message: TelegramMessage) -> IngestedChatMessage | None:
        log.t(f"Ingesting Telegram message: {message}")
        mapper = self.__di.telegram_domain_mapper
        if not self.__has_supported_content(message):
            log.d(f"Ignoring unsupported Telegram message '{message.message_id}'")
            return None

        # let's store the chat first, it's the basis ('save' deduplicates)
        stored_chat = self.__di.chat_config_repo.save(mapper.map_chat(message))

        # then we store the message author
        mapped_author = mapper.map_author(message)
        is_author_the_agent = bool(mapped_author and is_the_agent(mapped_author, ChatConfigDB.ChatType.telegram))
        stored_author = self.store_author(mapped_author)
        if stored_author and not is_author_the_agent:
            self.__di.chat_membership_service.ensure_for_inbound(stored_author, stored_chat)

        # then we store the message attachments
        stored_attachments: list[ChatAttachment] = []
        if is_author_the_agent:
            stored_attachments = self.__di.chat_attachment_repo.get_all_by_message(stored_chat.chat_id, str(message.message_id))
        else:
            if mapped_attachments := mapper.map_attachments(message):
                if stored_author is None:
                    raise InternalError("Telegram attachment cannot be stored without a message author", PLATFORM_MAPPING_FAILED)
                stored_attachments = [
                    self.store_attachment(
                        mapped_data = attachment,
                        chat_id = stored_chat.chat_id,
                        uploader_user_id = stored_author.id,
                    )
                    for attachment in mapped_attachments
                ]

        # finally we map, format, and store the message
        mapped_message = mapper.map_message(message)
        final_message_text = self.__format_message_text(
            mapped_data = mapped_message,
            chat_id = stored_chat.chat_id,
            attachments = stored_attachments,
        )
        stored_message = self.store_message(
            mapped_data = mapped_message,
            formatted_text = final_message_text,
            chat_id = stored_chat.chat_id,
            author_id = stored_author.id if stored_author else None,
        )
        return IngestedChatMessage(
            chat = stored_chat,
            author = stored_author,
            message = stored_message,
            attachments = stored_attachments,
            raw_message_text = mapped_message.text,
        )

    def __has_supported_content(self, message: TelegramMessage) -> bool:
        return bool(
            message.text
            or message.caption
            or message.audio
            or message.document
            or message.photo
            or message.video
            or message.voice,
        )

    def store_author(self, mapped_data: UserRemoteData | None) -> User | None:
        if not mapped_data:
            return None
        log.t(f"  Storing user: {mapped_data}")
        existing_user = self.__di.user_repo.get_by_remote_data(mapped_data)
        if existing_user:
            return self.__di.user_repo.save(apply_remote_data_user(existing_user, mapped_data))

        user = replace(
            from_remote_data_user(mapped_data),
            is_on_waitlist = self.__di.user_repo.count() >= config.max_users,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        return self.__di.user_repo.save(user)

    def store_message(
        self,
        mapped_data: ChatMessageRemoteData,
        formatted_text: str,
        chat_id: UUID,
        author_id: UUID | None,
    ) -> ChatMessage:
        log.t(f"  Storing chat message: {mapped_data}")
        old_chat_message = self.__di.chat_message_repo.get(chat_id, mapped_data.message_id)
        chat_message = (
            apply_remote_data_message(old_chat_message, mapped_data, author_id)
            if old_chat_message
            else from_remote_data_message(mapped_data, chat_id, author_id)
        )
        return self.__di.chat_message_repo.save(replace(chat_message, text = formatted_text))

    def store_attachment(
        self,
        mapped_data: ChatAttachmentRemoteData,
        chat_id: UUID,
        uploader_user_id: UUID,
    ) -> ChatAttachment:
        log.t(f"  Storing chat message attachment: {mapped_data}")
        attachment = from_remote_data_attachment(mapped_data, chat_id, uploader_user_id)
        content = self.__di.telegram_bot_api.download_file(attachment.external_id)
        if not content:
            raise ExternalServiceError(f"Couldn't download Telegram file '{attachment.external_id}'", MEDIA_DOWNLOAD_FAILED)
        return self.__di.chat_attachment_service.save(attachment, content)

    def __format_message_text(
        self,
        mapped_data: ChatMessageRemoteData,
        chat_id: UUID,
        attachments: list[ChatAttachment],
    ) -> str:
        formatted_message = FormattedChatMessage.from_text(mapped_data.text, attachments)
        if mapped_data.quote_text:
            formatted_message = formatted_message.prepend_quote(FormattedChatMessage.from_text(mapped_data.quote_text), depth = 1)
        if mapped_data.replied_to_message_id:
            replied_message = self.__di.chat_message_repo.get(chat_id, mapped_data.replied_to_message_id)
            if replied_message:
                replied_attachments = self.__di.chat_attachment_repo.get_all_by_message(
                    replied_message.chat_id,
                    replied_message.message_id,
                )
                formatted_message = formatted_message.prepend_quote(
                    FormattedChatMessage.from_text(replied_message.text, replied_attachments),
                )
            else:
                log.w(f"  Replied-to message '{mapped_data.replied_to_message_id}' not found in DB")
        return formatted_message.to_text()
