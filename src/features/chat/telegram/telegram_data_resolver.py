from dataclasses import replace
from uuid import UUID

from pydantic import BaseModel

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_mapper import from_remote_data as from_remote_data_attachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_mapper import apply_remote_data as apply_remote_data_message
from features.chat.message.chat_message_mapper import from_remote_data as from_remote_data_message
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.integrations.integrations import is_the_agent
from features.users.user import User
from features.users.user_mapper import apply_remote_data as apply_remote_data_user
from features.users.user_mapper import from_remote_data as from_remote_data_user
from features.users.user_remote_data import UserRemoteData
from util import log
from util.config import config
from util.error_codes import MEDIA_DOWNLOAD_FAILED, PLATFORM_MAPPING_FAILED
from util.errors import ExternalServiceError, InternalError


class TelegramDataResolver:
    """
    Resolves the final set of data attributes ready to be used by the service.
    If needed, this resolver will fetch more data from the API or the database.
    """

    class Result(BaseModel):
        chat: ChatConfig
        author: User | None
        message: ChatMessage
        attachments: list[ChatAttachment]

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def resolve(self, mapping_result: TelegramDomainMapper.Result) -> Result:
        log.t(f"Resolving mapping result: {mapping_result}")
        resolved_chat_config = self.__di.chat_config_repo.save(mapping_result.chat)
        resolved_author: User | None = None
        is_author_the_agent = False
        if mapping_result.author:
            is_author_the_agent = is_the_agent(mapping_result.author, ChatConfigDB.ChatType.telegram)
            resolved_author = self.resolve_author(
                replace(mapping_result.author, telegram_chat_id = None)
                if is_author_the_agent
                else mapping_result.author,
            )
        # ensure a membership row exists for real users (skip the agent itself)
        if resolved_author and not is_author_the_agent:
            self.__di.chat_membership_service.sync(resolved_author, resolved_chat_config)
        # we need to set the resolved chat's UUID to the message
        resolved_chat_message = self.resolve_chat_message(
            mapped_data = mapping_result.message,
            chat_id = resolved_chat_config.chat_id,
            author_id = resolved_author.id if resolved_author else None,
        )
        resolved_attachments: list[ChatAttachment] = []
        # skip attachment resolution for the agent's own messages — the SDK already archives outbound media
        if mapping_result.attachments and not is_author_the_agent:
            if not resolved_author or not resolved_author.id:
                raise InternalError("Telegram attachment cannot be resolved without a message author", PLATFORM_MAPPING_FAILED)
            resolved_attachments = [
                self.resolve_chat_attachment(
                    attachment,
                    resolved_chat_message.chat_id,
                    resolved_author.id,
                )
                for attachment in mapping_result.attachments
            ]
        return TelegramDataResolver.Result(
            chat = resolved_chat_config,
            author = resolved_author,
            message = resolved_chat_message,
            attachments = resolved_attachments,
        )

    # noinspection DuplicatedCode
    def resolve_author(self, mapped_data: UserRemoteData | None) -> User | None:
        if not mapped_data:
            return None
        log.t(f"  Resolving user: {mapped_data}")
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

    def resolve_chat_message(self, mapped_data: ChatMessageRemoteData, chat_id: UUID, author_id: UUID | None) -> ChatMessage:
        log.t(f"  Resolving chat message: {mapped_data}")
        old_chat_message = self.__di.chat_message_repo.get(chat_id, mapped_data.message_id)
        # reset the attributes that are not normally changed through the Telegram API
        chat_message = (
            apply_remote_data_message(old_chat_message, mapped_data, author_id)
            if old_chat_message
            else from_remote_data_message(mapped_data, chat_id, author_id)
        )
        return self.__di.chat_message_repo.save(chat_message)

    def resolve_chat_attachment(
        self,
        mapped_data: ChatAttachmentRemoteData,
        chat_id: UUID,
        uploader_user_id: UUID,
    ) -> ChatAttachment:
        log.t(f"  Resolving chat message attachment: {mapped_data}")
        draft_attachment = from_remote_data_attachment(mapped_data, chat_id, uploader_user_id)
        content = self.__di.telegram_bot_api.download_file(draft_attachment.external_id)
        if not content:
            raise ExternalServiceError(
                f"Could not download Telegram file '{draft_attachment.external_id}'", MEDIA_DOWNLOAD_FAILED,
            )
        return self.__di.chat_attachment_service.save(draft_attachment, content)
