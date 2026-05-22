from langchain_core.messages import AIMessage

from db.sql import get_detached_session
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.whatsapp.model.update import Update
from features.chat.whatsapp.whatsapp_data_resolver import WhatsAppDataResolver
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations import prompt_resolvers
from features.integrations.integrations import resolve_agent_user
from util import log
from util.config import config
from util.errors import ServiceError
from util.functions import silent


def respond_to_update(update: Update) -> bool:
    if config.log_whatsapp_update:
        log.t(f"Received a WhatsApp update: `{update}`")

    with get_detached_session() as db:
        di = DI(db)

        resolved_domain_data_all: list[WhatsAppDataResolver.Result] = []
        resolved_domain_data: WhatsAppDataResolver.Result | None = None
        try:
            # map to storage models for persistence
            domain_update = di.whatsapp_domain_mapper.map_update(update)
            if not domain_update:
                log.w("No messages to process in this WhatsApp update (likely a status update or notification)")
                return False

            # store and map to domain models (throws in case of error)
            resolved_domain_data_all = di.whatsapp_data_resolver.resolve_all(domain_update)
            # filter out messages without authors
            resolved_domain_data_all = [message for message in resolved_domain_data_all if message.author]
            if not resolved_domain_data_all:
                log.d("Not responding to messages without authors")
                return False
            # we inject DI context for the latest message only, so let's sort by timestamp
            resolved_domain_data = max(resolved_domain_data_all, key = lambda r: r.message.sent_at)
            di.inject_invoker(resolved_domain_data.author)
            di.inject_invoker_chat(resolved_domain_data.chat)

            # process the update using LLM; get instead of require to allow the first message to be sent
            tool = di.tool_choice_resolver.get_tool(ChatAgent.TOOL_TYPE, default_tool_for(ChatAgent.TOOL_TYPE))
            chat_agent = di.chat_agent(
                raw_last_message = resolved_domain_data.message.text,
                last_message_id = resolved_domain_data.message.message_id,
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
                di.whatsapp_bot_sdk.send_text_message(str(resolved_domain_data.chat.external_id), message.text)
                sent_messages += 1

            # mark the incoming message as read
            di.whatsapp_bot_sdk.mark_as_read(resolved_domain_data.message.message_id)

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
    resolved_domain_data: WhatsAppDataResolver.Result | None,
    error: Exception,
):
    if resolved_domain_data:
        emoji = error.emoji if isinstance(error, ServiceError) else "🤯"
        answer = AIMessage(prompt_resolvers.simple_chat_error(str(error), emoji = emoji))
        messages = di.domain_langchain_mapper.map_bot_message_to_storage(resolved_domain_data.chat, answer)
        for message in messages:
            di.whatsapp_bot_sdk.send_text_message(str(resolved_domain_data.chat.external_id), message.text)
        log.t("Replied with the error")
