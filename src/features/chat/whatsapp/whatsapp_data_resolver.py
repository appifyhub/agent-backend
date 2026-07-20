from dataclasses import dataclass, replace
from uuid import UUID

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
from features.chat.message.formatted_chat_message import FormattedChatMessage
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from features.integrations.integrations import is_the_agent
from features.users.user import User
from features.users.user_mapper import apply_remote_data as apply_remote_data_user
from features.users.user_mapper import from_remote_data as from_remote_data_user
from features.users.user_remote_data import UserRemoteData
from util import log
from util.config import config
from util.error_codes import MEDIA_DOWNLOAD_FAILED, PLATFORM_MAPPING_FAILED
from util.errors import ExternalServiceError, InternalError


class WhatsAppDataResolver:
    """
    Resolves the final set of data attributes ready to be used by the service.
    If needed, this resolver will fetch more data from the API or the database.
    """

    @dataclass(kw_only = True)
    class Result:
        chat: ChatConfig
        author: User | None
        message: ChatMessage
        attachments: list[ChatAttachment]

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def resolve_all(self, mapping_results: list[WhatsAppDomainMapper.Result]) -> list[Result]:
        log.t(f"Resolving all {len(mapping_results)} mapping results")
        # Sort by timestamp (oldest first) so replied-to messages are processed before replies
        sorted_results = sorted(mapping_results, key = lambda r: r.message.sent_at)
        return [self.resolve(mapping_result) for mapping_result in sorted_results]

    def resolve(self, mapping_result: WhatsAppDomainMapper.Result) -> Result:
        log.t(f"Resolving mapping result: {mapping_result}")
        resolved_chat_config = self.__di.chat_config_repo.save(mapping_result.chat)
        resolved_author: User | None = None
        is_author_the_agent = False
        if mapping_result.author:
            is_author_the_agent = is_the_agent(mapping_result.author, ChatConfigDB.ChatType.whatsapp)
            resolved_author = self.resolve_author(mapping_result.author)
        # ensure a membership row exists for real users (skip the agent itself)
        if resolved_author and not is_author_the_agent:
            self.__di.chat_membership_service.sync(resolved_author, resolved_chat_config)
        should_resolve_attachments = bool(mapping_result.attachments and not is_author_the_agent)
        if should_resolve_attachments:
            initial_message = self.__resolve_message_content(
                mapping_result = mapping_result,
                chat_id = resolved_chat_config.chat_id,
                attachments = [],
                should_replace_attachments = True,
            )
            self.resolve_chat_message(
                mapped_data = initial_message,
                chat_id = resolved_chat_config.chat_id,
                author_id = resolved_author.id if resolved_author else None,
            )
        resolved_attachments: list[ChatAttachment] = []
        # skip attachment resolution for the agent's own messages — the SDK already archives outbound media
        if should_resolve_attachments:
            if not resolved_author or not resolved_author.id:
                raise InternalError("WhatsApp attachment cannot be resolved without a message author", PLATFORM_MAPPING_FAILED)
            resolved_attachments = [
                self.resolve_chat_attachment(
                    attachment,
                    resolved_chat_config.chat_id,
                    resolved_author.id,
                )
                for attachment in mapping_result.attachments
            ]
        remote_message = self.__resolve_message_content(
            mapping_result = mapping_result,
            chat_id = resolved_chat_config.chat_id,
            attachments = resolved_attachments,
            should_replace_attachments = should_resolve_attachments,
        )
        # we need to set the resolved chat's UUID to the message
        resolved_chat_message = self.resolve_chat_message(
            mapped_data = remote_message,
            chat_id = resolved_chat_config.chat_id,
            author_id = resolved_author.id if resolved_author else None,
        )
        return WhatsAppDataResolver.Result(
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
        # reset the attributes that are not normally changed through the WhatsApp API
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
        attachment = from_remote_data_attachment(mapped_data, chat_id, uploader_user_id)
        content = self.__di.whatsapp_bot_api.download_media(attachment.external_id)
        if not content:
            raise ExternalServiceError(f"Could not download WhatsApp media '{attachment.external_id}'", MEDIA_DOWNLOAD_FAILED)
        return self.__di.chat_attachment_service.save(attachment, content)

    def __resolve_message_content(
        self,
        mapping_result: WhatsAppDomainMapper.Result,
        chat_id: UUID,
        attachments: list[ChatAttachment],
        should_replace_attachments: bool,
    ) -> ChatMessageRemoteData:
        formatted_message = mapping_result.formatted_message or FormattedChatMessage.from_text(mapping_result.message.text)
        if should_replace_attachments:
            formatted_message = formatted_message.with_attachments(attachments)
        if mapping_result.replied_to_message_id:
            replied_message = self.__di.chat_message_repo.get(chat_id, mapping_result.replied_to_message_id)
            if replied_message:
                replied_attachments = self.__di.chat_attachment_repo.get_all_by_message(
                    replied_message.chat_id,
                    replied_message.message_id,
                )
                formatted_message = formatted_message.prepend_quote(
                    FormattedChatMessage.from_text(replied_message.text, replied_attachments),
                )
            else:
                log.w(f"  Replied-to message '{mapping_result.replied_to_message_id}' not found in DB")
        return ChatMessageRemoteData(
            message_id = mapping_result.message.message_id,
            sent_at = mapping_result.message.sent_at,
            text = formatted_message.to_text(),
        )
