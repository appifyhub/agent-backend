from uuid import UUID

from pydantic import BaseModel

from db.model.chat_config import ChatConfigDB
from db.schema.chat_message import ChatMessage, ChatMessageSave
from db.schema.user import User, UserSave
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_mapper import apply_remote_data, from_remote_data
from features.chat.attachment.chat_message_attachment_remote_data import ChatMessageAttachmentRemoteData
from features.chat.config.chat_config import ChatConfig
from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
from features.integrations.integrations import is_the_agent
from util import log
from util.config import config
from util.error_codes import UNEXPECTED_ERROR
from util.errors import InternalError


class WhatsAppDataResolver:
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
            if resolved_author:
                mapping_result.message.author_id = resolved_author.id
        # ensure a membership row exists for real users (skip the agent itself)
        if resolved_author and not is_author_the_agent:
            self.__di.chat_membership_service.sync(resolved_author, resolved_chat_config)
        # we need to set the resolved chat's UUID to the message
        mapping_result.message.chat_id = resolved_chat_config.chat_id
        # Handle replied-to message (WhatsApp doesn't provide content, so we fetch from DB)
        if mapping_result.replied_to_message_id:
            replied_message_db = self.__di.chat_message_crud.get(
                chat_id = resolved_chat_config.chat_id,
                message_id = mapping_result.replied_to_message_id,
            )
            if replied_message_db:
                replied_message = ChatMessage.model_validate(replied_message_db)
                quoted_text = self.__format_quoted_message(replied_message.text)
                mapping_result.message.text = f"{quoted_text}\n\n{mapping_result.message.text}"
            else:
                log.w(f"  Replied-to message '{mapping_result.replied_to_message_id}' not found in DB")
        resolved_chat_message = self.resolve_chat_message(mapping_result.message)
        resolved_attachments = [
            self.resolve_chat_message_attachment(attachment, resolved_chat_message.chat_id)
            for attachment in mapping_result.attachments
        ]
        return WhatsAppDataResolver.Result(
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
        whatsapp_phone_number = mapped_data.whatsapp_phone_number.get_secret_value() if mapped_data.whatsapp_phone_number else ""
        old_user_db = (
            self.__di.user_crud.get_by_whatsapp_user_id(mapped_data.whatsapp_user_id or "") or
            self.__di.user_crud.get_by_whatsapp_phone_number(whatsapp_phone_number or "")
        )

        if old_user_db:
            old_user = User.model_validate(old_user_db)
            # reset the attributes that are not normally changed through the WhatsApp API
            mapped_data.id = old_user.id
            mapped_data.full_name = mapped_data.full_name if not old_user.full_name else old_user.full_name
            mapped_data.about_me = old_user.about_me
            mapped_data.custom_prompt = old_user.custom_prompt
            mapped_data.whatsapp_phone_number = mapped_data.whatsapp_phone_number or old_user.whatsapp_phone_number
            mapped_data.telegram_chat_id = old_user.telegram_chat_id
            mapped_data.telegram_user_id = old_user.telegram_user_id
            mapped_data.telegram_username = old_user.telegram_username
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

    def resolve_chat_message(self, mapped_data: ChatMessageSave) -> ChatMessage:
        log.t(f"  Resolving chat message: {mapped_data}")
        if mapped_data.chat_id is None:
            raise InternalError("chat_id is None in resolved chat message", UNEXPECTED_ERROR)
        old_chat_message_db = self.__di.chat_message_crud.get(mapped_data.chat_id, mapped_data.message_id)
        if old_chat_message_db:
            old_chat_message = ChatMessage.model_validate(old_chat_message_db)
            # reset the attributes that are not normally changed through the WhatsApp API
            mapped_data.chat_id = old_chat_message.chat_id
            mapped_data.author_id = mapped_data.author_id or old_chat_message.author_id
            mapped_data.sent_at = mapped_data.sent_at or old_chat_message.sent_at
        return ChatMessage.model_validate(self.__di.chat_message_crud.save(mapped_data))

    def resolve_chat_message_attachment(
        self,
        mapped_data: ChatMessageAttachmentRemoteData,
        chat_id: UUID,
    ) -> ChatMessageAttachment:
        log.t(f"  Resolving chat message attachment: {mapped_data}")
        old_attachment = self.__di.chat_message_attachment_repo.get_by_external_id(mapped_data.external_id)
        attachment = apply_remote_data(old_attachment, mapped_data) if old_attachment else from_remote_data(mapped_data, chat_id)
        return self.__di.whatsapp_bot_sdk.refresh_attachment(attachment)

    # noinspection PyMethodMayBeStatic
    def __format_quoted_message(self, text: str) -> str:
        all_lines = text.split("\n")
        prefixed_lines = [f">>>> {line}" for line in all_lines]
        return "\n".join(prefixed_lines)
