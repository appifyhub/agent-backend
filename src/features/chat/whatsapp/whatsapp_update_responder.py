from datetime import datetime
from time import sleep

from langchain_core.messages import AIMessage

from db.sql import get_detached_session
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.whatsapp.model.update import Update
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations import prompt_resolvers
from features.integrations.integrations import format_reaction_response, is_reaction_response, resolve_agent_user
from util import log
from util.config import config
from util.errors import ServiceError
from util.functions import parse_ai_message_content, silent


def respond_to_update(update: Update) -> bool:
    if config.log_whatsapp_update:
        log.t(f"Received a WhatsApp update: `{update}`")

    with get_detached_session() as db:
        di = DI(db)

        resolved_domain_data_all: list[IngestedChatMessage] = []
        resolved_domain_data: IngestedChatMessage | None = None
        try:
            # store and map to domain models (throws in case of error)
            resolved_domain_data_all = di.whatsapp_chat_inbound_service.ingest_update(update)
            if not resolved_domain_data_all:
                log.w("No messages to process in this WhatsApp update (likely a status update or notification)")
                return False

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
                raw_last_message = resolved_domain_data.raw_message_text,
                last_message_id = resolved_domain_data.message.message_id,
                configured_tool = tool,
            )
            answer = chat_agent.execute()
            if not answer or not answer.content:
                log.d("No LLM response needed (command handled or no reply required)")
                return False

            # send and store the response[s]
            sent_messages: int = 0
            agent = resolve_agent_user(resolved_domain_data.chat.chat_type)
            as_reaction = parse_ai_message_content(answer)
            if is_reaction_response(as_reaction, resolved_domain_data.chat.chat_type):
                di.chat_message_repo.save(
                    ChatMessage(
                        chat_id = resolved_domain_data.chat.chat_id,
                        message_id = f"reaction:{resolved_domain_data.message.message_id}",
                        author_id = agent.id,
                        sent_at = datetime.now(),
                        text = format_reaction_response(as_reaction),
                    ),
                )
                silent(di.platform_bot_sdk().set_reaction)(
                    str(resolved_domain_data.chat.external_id),
                    resolved_domain_data.message.message_id,
                    as_reaction,
                )
                log.i(f"Reacted to message {resolved_domain_data.message.message_id} with {as_reaction}")
            else:
                domain_messages = di.domain_langchain_mapper.map_bot_message_to_storage(resolved_domain_data.chat, answer)
                for message in domain_messages:
                    di.whatsapp_bot_sdk.send_text_message(resolved_domain_data.chat, message.text)
                    sleep(0.1)
                    sent_messages += 1

            # mark the incoming message as read
            di.whatsapp_bot_sdk.mark_as_read(resolved_domain_data.message.message_id)

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
    resolved_domain_data: IngestedChatMessage | None,
    error: Exception,
):
    if resolved_domain_data:
        emoji = error.emoji if isinstance(error, ServiceError) else "🤯"
        answer = AIMessage(prompt_resolvers.simple_chat_error(str(error), emoji = emoji))
        messages = di.domain_langchain_mapper.map_bot_message_to_storage(resolved_domain_data.chat, answer)
        for message in messages:
            di.whatsapp_bot_sdk.send_text_message(resolved_domain_data.chat, message.text)
            sleep(0.1)
        log.t("Replied with the error")
