import asyncio
from datetime import datetime
from time import sleep

from langchain_core.messages import AIMessage

from db.model.chat_config import ChatConfigDB
from db.sql import get_detached_session
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.config.chat_config import ChatConfig
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.message_burst import ClaimedChatMessageBurst, ScheduledChatMessageBurst
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations import prompt_resolvers
from features.integrations.integrations import (
    format_reaction_response,
    is_reaction_response,
    resolve_agent_user,
    resolve_external_handle,
)
from util import log
from util.config import config
from util.error_codes import UNSUPPORTED_CHAT_TYPE
from util.errors import ConfigurationError, ServiceError
from util.functions import parse_ai_message_content, silent


class MessageBurstService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def is_explicitly_addressed(
        self,
        message_text: str,
        chat_type: ChatConfigDB.ChatType,
    ) -> bool:
        agent = resolve_agent_user(chat_type)
        agent_handle = resolve_external_handle(agent, chat_type)
        if not agent_handle:
            return False
        non_quoted_text = "\n".join(
            line
            for line in message_text.splitlines()
            if not line.lstrip().startswith(">>")
        )
        return f"@{agent_handle}" in non_quoted_text

    def record(
        self,
        message: ChatMessage,
        is_addressed: bool,
    ) -> ScheduledChatMessageBurst:
        return self.__di.chat_message_burst_repo.record_message(
            message = message,
            is_addressed = is_addressed,
            quiet_period_s = config.chat_burst_quiet_period_s,
        )

    def load_claimed_message(
        self,
        claim: ClaimedChatMessageBurst,
    ) -> IngestedChatMessage | None:
        chat = self.__di.chat_config_repo.get(claim.chat_id)
        author = self.__di.user_repo.get(claim.author_id)
        message = self.__di.chat_message_repo.get_by_ingestion_order(
            claim.chat_id,
            claim.last_message_ingestion_order,
        )

        if chat is None or author is None or message is None:
            log.w(
                f"Could not load claimed burst with {claim.message_count} messages "
                f"for chat {claim.chat_id.hex}",
            )
            return None

        attachments = self.__di.chat_attachment_repo.get_all_by_message(
            message.chat_id,
            message.message_id,
        )
        return IngestedChatMessage(
            chat = chat,
            author = author,
            message = message,
            attachments = attachments,
            raw_message_text = message.text,
        )

    def process_message(
        self,
        resolved_domain_data: IngestedChatMessage,
        claim: ClaimedChatMessageBurst | None = None,
        command_only: bool = False,
    ) -> bool:
        should_notify_of_errors = False
        try:
            # build the agent against the claimed history cutoff
            tool = self.__di.tool_choice_resolver.get_tool(
                ChatAgent.TOOL_TYPE,
                default_tool_for(ChatAgent.TOOL_TYPE),
            )
            chat_agent = self.__di.chat_agent(
                trigger_message_text = resolved_domain_data.raw_message_text,
                trigger_message_id = resolved_domain_data.message.message_id,
                configured_tool = tool,
                cutoff_sent_at = claim.last_message_sent_at if claim else resolved_domain_data.message.sent_at,
                cutoff_ingestion_order = (
                    claim.last_message_ingestion_order
                    if claim
                    else resolved_domain_data.message.ingestion_order
                ),
                explicitly_addressed = claim.is_addressed if claim else True,
            )

            if command_only:
                command_result = chat_agent.process_commands()
                if not command_result.is_handled or command_result.reply is None:
                    return False
                answer = command_result.reply
            else:
                answer = chat_agent.execute()

            if not answer or not answer.content:
                log.d("No LLM response needed (command handled or no reply required)")
                return False

            self.__di.rollback_db_session()

            # deliver the agent response through the current chat platform
            sent_messages: int = 0
            agent = resolve_agent_user(resolved_domain_data.chat.chat_type)
            as_reaction = parse_ai_message_content(answer)
            if is_reaction_response(as_reaction, resolved_domain_data.chat.chat_type):
                self.__di.chat_message_repo.save(
                    ChatMessage(
                        chat_id = resolved_domain_data.chat.chat_id,
                        message_id = f"reaction:{resolved_domain_data.message.message_id}",
                        author_id = agent.id,
                        sent_at = datetime.now(),
                        text = format_reaction_response(as_reaction),
                    ),
                )
                self.__di.rollback_db_session()
                silent(self.__di.platform_bot_sdk().set_reaction)(
                    str(resolved_domain_data.chat.external_id),
                    resolved_domain_data.message.message_id,
                    as_reaction,
                )
                log.i(f"Reacted to message {resolved_domain_data.message.message_id} with {as_reaction}")
            else:
                domain_messages = self.__di.domain_langchain_mapper.map_bot_message_to_storage(
                    resolved_domain_data.chat,
                    answer,
                )
                for message in domain_messages:
                    should_notify_of_errors = True
                    self.__send_text_message(resolved_domain_data.chat, message.text)
                    self.__di.rollback_db_session()
                    sleep(0.1)
                    sent_messages += 1

            if resolved_domain_data.chat.chat_type == ChatConfigDB.ChatType.whatsapp:
                self.__di.whatsapp_bot_sdk.mark_as_read(resolved_domain_data.message.message_id)

            log.t(f"Finished responding to updates. \n[{agent.full_name}]: {answer.content}")
            log.i(f"Sent {sent_messages} messages")
            return True
        except Exception as e:
            log.e("Failed to process message", e)
            if should_notify_of_errors:
                self.__di.rollback_db_session()
                self.__notify_of_errors(resolved_domain_data, e)
            return False

    async def process_after_quiet_period(
        self,
        scheduled: ScheduledChatMessageBurst,
    ) -> bool:
        processed = False
        while True:
            # wait without retaining a database session
            await asyncio.sleep(scheduled.wait_seconds)

            claimed = await asyncio.to_thread(self.__claim, scheduled)
            if claimed is None:
                return processed

            try:
                processed = await asyncio.to_thread(self.__process_claimed_burst, claimed) or processed
            finally:
                scheduled = await asyncio.to_thread(self.__finalize, claimed)
            if scheduled is None:
                return processed

    def __process_claimed_burst(self, claim: ClaimedChatMessageBurst) -> bool:
        try:
            with get_detached_session() as db:
                di = self.__di.clone(db)
                service = di.message_burst_service

                resolved_domain_data = service.load_claimed_message(claim)
                if resolved_domain_data is None:
                    return False

                di.inject_invoker(resolved_domain_data.author)
                di.inject_invoker_chat(resolved_domain_data.chat)
                return service.process_message(resolved_domain_data, claim = claim)
        except Exception as e:
            log.e(f"Failed to process burst with {claim.message_count} messages", e)
            return False

    def __send_text_message(
        self,
        chat: ChatConfig,
        text: str,
    ) -> None:
        match chat.chat_type:
            case ChatConfigDB.ChatType.telegram:
                self.__di.telegram_bot_sdk.send_text_message(chat, text)
            case ChatConfigDB.ChatType.whatsapp:
                self.__di.whatsapp_bot_sdk.send_text_message(chat, text)
            case _:
                raise ConfigurationError(
                    f"Unsupported chat type: {chat.chat_type}",
                    UNSUPPORTED_CHAT_TYPE,
                )

    @silent
    def __notify_of_errors(
        self,
        resolved_domain_data: IngestedChatMessage,
        error: Exception,
    ) -> None:
        emoji = error.emoji if isinstance(error, ServiceError) else "🤯"
        answer = AIMessage(prompt_resolvers.simple_chat_error(str(error), emoji = emoji))
        messages = self.__di.domain_langchain_mapper.map_bot_message_to_storage(
            chat = resolved_domain_data.chat,
            message = answer,
        )
        for message in messages:
            self.__send_text_message(resolved_domain_data.chat, message.text)
            self.__di.rollback_db_session()
            sleep(0.1)
        log.t("Replied with the error")

    def __claim(self, scheduled: ScheduledChatMessageBurst) -> ClaimedChatMessageBurst | None:
        with get_detached_session() as db:
            return self.__di.clone(db).chat_message_burst_repo.claim(scheduled)

    def __finalize(self, claimed: ClaimedChatMessageBurst) -> ScheduledChatMessageBurst | None:
        with get_detached_session() as db:
            return self.__di.clone(db).chat_message_burst_repo.finalize(claimed)
