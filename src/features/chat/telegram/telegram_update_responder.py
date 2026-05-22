from fastapi import HTTPException
from langchain_core.messages import AIMessage

from db.sql import get_detached_session
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.telegram.model.update import Update
from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations import prompt_resolvers
from features.integrations.integrations import resolve_agent_user
from util import log
from util.config import config
from util.errors import ServiceError
from util.functions import silent


def respond_to_update(update: Update) -> bool:
    if config.log_telegram_update:
        log.t(f"Received a Telegram update: `{update}`")

    with get_detached_session() as db:
        di = DI(db)

        resolved_domain_data: TelegramDataResolver.Result | None = None
        try:
            # map to storage models for persistence
            domain_update = di.telegram_domain_mapper.map_update(update)
            if not domain_update:
                raise HTTPException(status_code = 422, detail = "Unable to map the Telegram update")

            # store and map to domain models (throws in case of error)
            resolved_domain_data = di.telegram_data_resolver.resolve(domain_update)
            if not resolved_domain_data.author:
                log.d("Not responding to messages without author")
                return False
            di.inject_invoker(resolved_domain_data.author)
            di.inject_invoker_chat(resolved_domain_data.chat)

            # process the update using LLM; get instead of require to allow the first message to be sent
            tool = di.tool_choice_resolver.get_tool(ChatAgent.TOOL_TYPE, default_tool_for(ChatAgent.TOOL_TYPE))
            chat_agent = di.chat_agent(
                raw_last_message = domain_update.message.text,
                last_message_id = domain_update.message.message_id,
                configured_tool = tool,
            )
            answer = chat_agent.execute()
            if not answer or not answer.content:
                log.d("No LLM response needed (command handled or no reply required)")
                return False

            # send and store the response[s]
            sent_messages: int = 0
            domain_messages = di.domain_langchain_mapper.map_bot_message_to_storage(resolved_domain_data.chat, answer)
            for message in domain_messages:
                di.telegram_bot_sdk.send_text_message(str(resolved_domain_data.chat.external_id), message.text)
                sent_messages += 1

            agent = resolve_agent_user(resolved_domain_data.chat.chat_type)
            log.t(f"Finished responding to updates. \n[{agent.full_name}]: {answer.content}")
            log.i(f"Sent {sent_messages} messages")
            return True
        except Exception as e:
            log.e(f"Failed to ingest: {update}", e)
            __notify_of_errors(di, resolved_domain_data, e)
            return False


@silent
def __notify_of_errors(
    di: DI,
    resolved_domain_data: TelegramDataResolver.Result | None,
    error: Exception,
):
    if resolved_domain_data:
        emoji = error.emoji if isinstance(error, ServiceError) else "🤯"
        answer = AIMessage(prompt_resolvers.simple_chat_error(str(error), emoji = emoji))
        messages = di.domain_langchain_mapper.map_bot_message_to_storage(resolved_domain_data.chat, answer)
        for message in messages:
            di.telegram_bot_sdk.send_text_message(str(resolved_domain_data.chat.external_id), message.text)
        log.t("Replied with the error")
