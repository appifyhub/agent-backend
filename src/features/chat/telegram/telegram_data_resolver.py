from uuid import UUID

from pydantic import BaseModel

from db.model.chat_config import ChatConfigDB
from db.schema.user import User, UserSave
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_mapper import apply_remote_data as apply_remote_data_attachment
from features.chat.attachment.chat_message_attachment_mapper import from_remote_data as from_remote_data_attachment
from features.chat.attachment.chat_message_attachment_remote_data import ChatMessageAttachmentRemoteData
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_mapper import apply_remote_data as apply_remote_data_message
from features.chat.message.chat_message_mapper import from_remote_data as from_remote_data_message
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.integrations.integrations import is_the_agent
from util import log
from util.config import config


class TelegramDataResolver:
    """
    Resolves the final set of data attributes ready to be used by the service.
    If needed, this resolver will fetch more data from the API or the database.
    """

    class Result(BaseModel):
        chat: ChatConfig
        author: User | None
        message: ChatMessage
        attachments: list[ChatMessageAttachment]

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
            if is_author_the_agent:
                mapping_result.author.telegram_chat_id = None  # bot has no private chat
            resolved_author = self.resolve_author(mapping_result.author)
        # ensure a membership row exists for real users (skip the agent itself)
        if resolved_author and not is_author_the_agent:
            self.__di.chat_membership_service.sync(resolved_author, resolved_chat_config)
        # we need to set the resolved chat's UUID to the message
        resolved_chat_message = self.resolve_chat_message(
            mapped_data = mapping_result.message,
            chat_id = resolved_chat_config.chat_id,
            author_id = resolved_author.id if resolved_author else None,
        )
        resolved_attachments = [
            self.resolve_chat_message_attachment(attachment, resolved_chat_message.chat_id)
            for attachment in mapping_result.attachments
        ]
        return TelegramDataResolver.Result(
            chat = resolved_chat_config,
            author = resolved_author,
            message = resolved_chat_message,
            attachments = resolved_attachments,
        )

    # noinspection DuplicatedCode
    def resolve_author(self, mapped_data: UserSave | None) -> User | None:
        if not mapped_data:
            return None
        log.t(f"  Resolving user: {mapped_data}")
        old_user_db = (
            self.__di.user_crud.get_by_telegram_user_id(mapped_data.telegram_user_id or -1) or
            self.__di.user_crud.get_by_telegram_username(mapped_data.telegram_username or "")
        )

        if old_user_db:
            old_user = User.model_validate(old_user_db)
            # reset the attributes that are not normally changed through the Telegram API
            mapped_data.id = old_user.id
            mapped_data.full_name = mapped_data.full_name if not old_user.full_name else old_user.full_name
            mapped_data.about_me = old_user.about_me
            mapped_data.custom_prompt = old_user.custom_prompt
            mapped_data.telegram_chat_id = mapped_data.telegram_chat_id or old_user.telegram_chat_id
            mapped_data.whatsapp_user_id = old_user.whatsapp_user_id
            mapped_data.whatsapp_phone_number = old_user.whatsapp_phone_number
            mapped_data.connect_key = old_user.connect_key
            mapped_data.open_ai_key = old_user.open_ai_key
            mapped_data.anthropic_key = old_user.anthropic_key
            mapped_data.google_ai_key = old_user.google_ai_key
            mapped_data.perplexity_key = old_user.perplexity_key
            mapped_data.replicate_key = old_user.replicate_key
            mapped_data.rapid_api_key = old_user.rapid_api_key
            mapped_data.coinmarketcap_key = old_user.coinmarketcap_key
            mapped_data.x_key = old_user.x_key
            mapped_data.x_ai_key = old_user.x_ai_key
            mapped_data.tool_choice_chat = old_user.tool_choice_chat
            mapped_data.tool_choice_reasoning = old_user.tool_choice_reasoning
            mapped_data.tool_choice_copywriting = old_user.tool_choice_copywriting
            mapped_data.tool_choice_vision = old_user.tool_choice_vision
            mapped_data.tool_choice_hearing = old_user.tool_choice_hearing
            mapped_data.tool_choice_images_gen = old_user.tool_choice_images_gen
            mapped_data.tool_choice_images_edit = old_user.tool_choice_images_edit
            mapped_data.tool_choice_search = old_user.tool_choice_search
            mapped_data.tool_choice_embedding = old_user.tool_choice_embedding
            mapped_data.tool_choice_api_fiat_exchange = old_user.tool_choice_api_fiat_exchange
            mapped_data.tool_choice_api_crypto_exchange = old_user.tool_choice_api_crypto_exchange
            mapped_data.tool_choice_api_twitter = old_user.tool_choice_api_twitter
            mapped_data.credit_balance = old_user.credit_balance
            mapped_data.is_on_waitlist = old_user.is_on_waitlist
            mapped_data.is_invited_to_start = old_user.is_invited_to_start
            mapped_data.are_policies_accepted = old_user.are_policies_accepted
            mapped_data.group = old_user.group
        else:
            user_count = self.__di.user_crud.count()
            at_capacity = user_count >= config.max_users
            mapped_data.is_on_waitlist = at_capacity
            mapped_data.is_invited_to_start = False
            mapped_data.are_policies_accepted = False

        return User.model_validate(self.__di.user_crud.save(mapped_data))

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

    def resolve_chat_message_attachment(
        self,
        mapped_data: ChatMessageAttachmentRemoteData,
        chat_id: UUID,
    ) -> ChatMessageAttachment:
        log.t(f"  Resolving chat message attachment: {mapped_data}")
        old_attachment = self.__di.chat_message_attachment_repo.get_by_external_id(mapped_data.external_id)
        attachment = (
            apply_remote_data_attachment(old_attachment, mapped_data)
            if old_attachment
            else from_remote_data_attachment(mapped_data, chat_id)
        )
        return self.__di.telegram_bot_sdk.refresh_attachment(attachment)
