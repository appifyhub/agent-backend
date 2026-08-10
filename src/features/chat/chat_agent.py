import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.command_processor import is_known_command
from features.chat.message.chat_message import ChatMessage
from features.chat.message.formatted_chat_message import ATTACHMENT_PLACEHOLDER_REGEX
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from features.integrations.integrations import resolve_agent_user, resolve_external_handle, resolve_private_chat_id
from util import log
from util.config import config
from util.error_codes import (
    LLM_UNEXPECTED_RESPONSE,
    NOT_CHAT_MEMBER,
    TOOL_NOT_FOUND,
    UNEXPECTED_ERROR,
)
from util.errors import AuthorizationError, ExternalServiceError, InternalError, NotFoundError, ServiceError

TMessage = TypeVar("TMessage", bound = BaseMessage)  # Generic message type
TooledChatModel = Runnable[LanguageModelInput, BaseMessage]


class ChatAgent:

    @dataclass
    class CommandHandlingResult:
        is_handled: bool
        reply: AIMessage | None = None

    TOOL_TYPE: ToolType = ToolType.chat

    __messages: list[BaseMessage]
    __trigger_message_text: str  # excludes the resolver formatting
    __trigger_message_id: str
    __trigger_message_sent_at: datetime
    __configured_tool: ConfiguredTool | None
    __max_iterations: int
    __di: DI

    def __init__(
        self,
        trigger_message_text: str,
        trigger_message_id: str,
        trigger_message_sent_at: datetime,
        configured_tool: ConfiguredTool | None,
        di: DI,
    ):
        target_chat = di.require_invoker_chat()
        chat_type = di.require_invoker_chat_type()
        invoker_membership = di.chat_membership_service.get(di.invoker.id, target_chat.chat_id)
        if invoker_membership is None:
            raise AuthorizationError(f"User {di.invoker.id} is not a member of chat {target_chat.chat_id}", NOT_CHAT_MEMBER)

        # initialize the basic properties
        self.__trigger_message_text = trigger_message_text
        self.__trigger_message_id = trigger_message_id
        self.__trigger_message_sent_at = trigger_message_sent_at
        self.__max_iterations = invoker_membership.max_iterations
        self.__configured_tool = configured_tool
        self.__di = di

        # load the chat history
        past_messages = di.chat_message_repo.get_latest_by_chat(
            chat_id = target_chat.chat_id,
            limit = invoker_membership.max_chat_history_depth,
        )
        langchain_messages = [self.__map_to_langchain(di, message, chat_type) for message in past_messages][::-1]
        system_prompt = prompt_resolvers.chat(
            invoker = di.invoker,
            target_chat = target_chat,
            invoker_membership = invoker_membership,
            tools_list = str(di.llm_tool_library.tool_names),
        )
        self.__messages = [SystemMessage(system_prompt)]
        self.__messages.extend(langchain_messages)

    @staticmethod
    def __map_to_langchain(di: DI, message: ChatMessage, chat_type: ChatConfigDB.ChatType) -> HumanMessage | AIMessage:
        author = di.user_repo.get(message.author_id)
        return di.domain_langchain_mapper.map_to_langchain(
            author = author,
            message = message,
            chat_type = chat_type,
        )

    def __add_message(self, message: TMessage) -> TMessage:
        self.__messages.append(message)
        return message

    @property
    def __last_message(self) -> BaseMessage:
        return self.__messages[-1]

    def __is_superseded_by_newer_invoker_message(self) -> bool:
        if config.chat_debounce_delay_s <= 0.0:
            return False
        self.__di.rollback_db_session()  # we release the DB before sleeping
        time.sleep(config.chat_debounce_delay_s)
        chat_id = self.__di.require_invoker_chat().chat_id
        # iterate newest-to-oldest, skipping messages from other authors, to find the
        # most recent message from this invoker - only the same author messages form a burst
        try:
            recent_messages = self.__di.chat_message_repo.get_latest_by_chat(chat_id, limit = 10)
            for message in recent_messages:
                if message.author_id == self.__di.invoker.id and self.__is_newer_message(message):
                    log.d(f"Message burst detected: skipping message '{self.__trigger_message_id}'")
                    return True
            return False
        finally:
            self.__di.rollback_db_session()

    def __is_newer_message(self, message: ChatMessage) -> bool:
        if message.sent_at > self.__trigger_message_sent_at:
            return True
        if message.sent_at < self.__trigger_message_sent_at:
            return False
        if message.message_id == self.__trigger_message_id:
            return False
        if message.message_id.isdigit() and self.__trigger_message_id.isdigit():
            return int(message.message_id) > int(self.__trigger_message_id)
        return True

    def __route_error_to_user(self, error_text: str, emoji: str = "🤯") -> AIMessage:
        fallback = AIMessage(prompt_resolvers.simple_chat_error(error_text, emoji = emoji))
        try:
            chat_type = self.__di.require_invoker_chat_type()
            private_chat_id = resolve_private_chat_id(self.__di.invoker, chat_type)
            if not private_chat_id:
                return fallback
            self.__di.platform_bot_sdk().send_text_message(private_chat_id, f"{emoji}\n\n{error_text}")
            settings_link = self.__di.settings_controller.create_settings_link().settings_link
            self.__di.platform_bot_sdk().send_button_link(private_chat_id, settings_link)
            return AIMessage(emoji)
        except Exception as e:
            log.w("Failed to route error to private chat", e)
            return fallback

    def execute(self) -> AIMessage | None:
        log.t(f"Starting chat completion for '{self.__last_message.content}'")

        # drop empty or self-authored messages before anything else
        if not self.__is_dispatchable():
            return None

        # commands run eagerly when the bot is directly addressed, so a later
        # message in the same burst does not swallow the command
        if self.__is_addressable():
            command_handling = self.process_commands()
            if command_handling.is_handled:
                return command_handling.reply

        # burst gate: only the latest message in a burst reaches LLM processing
        if self.__is_superseded_by_newer_invoker_message():
            return None

        # full reply decision runs on the burst winner with burst-aware mention
        if not self.should_reply():
            return None

        # handle user profile constraints next
        try:
            self.__di.authorization_service.require_user_is_chat_ready(self.__di.invoker)
        except ServiceError as e:
            return self.__route_error_to_user(str(e), emoji = e.emoji)
        finally:
            self.__di.rollback_db_session()

        # handle access control before doing any LLM processing
        if not self.__configured_tool:
            log.w(f"No configured tool found for #{self.__di.invoker.id.hex}, skipping LLM processing")
            return self.__route_error_to_user("Not configured.")

        # prepare the LLM model and connected tools
        progress_notifier = self.__di.chat_progress_notifier(self.__trigger_message_id)
        base_model = self.__di.chat_langchain_model(self.__configured_tool)
        tools_model: None | TooledChatModel = None
        try:
            tools_model = self.__di.llm_tool_library.bind_tools(base_model)
        except Exception as e:
            log.w("Failed to bind tools to the LLM model, using base model", e)

        # main flow: process the messages using the LLM
        try:
            iteration = 1
            progress_notifier.start()
            while True:
                # don't blow up the costs
                if iteration > self.__max_iterations:
                    raise InternalError(f"Reached max iterations ({self.__max_iterations}), finishing", UNEXPECTED_ERROR)

                # run the actual LLM completion
                llm_answer = (tools_model or base_model).invoke(self.__messages)
                answer = self.__add_message(llm_answer)

                # noinspection Pydantic
                if not answer.tool_calls:  # type: ignore
                    log.d(f"Iteration #{iteration} has no tool calls.")
                    if not isinstance(answer, AIMessage):
                        raise ExternalServiceError(f"Received a non-AI message from LLM: {answer}", LLM_UNEXPECTED_RESPONSE)
                    self.__remove_attachment_placeholder_content(answer)
                    log.i(f"Finishing chat response with {len(answer.content)} characters")
                    return answer

                log.d(f"Iteration #{iteration} has tool calls, processing...")
                iteration += 1

                # noinspection Pydantic
                for tool_call in answer.tool_calls:  # type: ignore
                    tool_id: Any = tool_call["id"]
                    tool_name: Any = tool_call["name"]
                    tool_args: Any = tool_call["args"]

                    log.t(f"  Processing {tool_id} / '{tool_name}' tool call")
                    tool_result: str | None = self.__di.llm_tool_library.invoke(tool_name, tool_args)
                    if not tool_result:
                        log.w(f"Tool {tool_name} not invoked!")
                        continue
                    self.__add_message(ToolMessage(tool_result, tool_call_id = tool_id))

                if not isinstance(self.__last_message, ToolMessage):
                    raise NotFoundError("Couldn't find tools to invoke!", TOOL_NOT_FOUND)
        except ServiceError as e:
            log.e("Chat completion failed (recognized error)", e)
            return self.__route_error_to_user(str(e), emoji = e.emoji)
        except Exception as e:
            log.e("Chat completion failed (unrecognized error)", e)
            emoji = e.emoji if isinstance(e, ServiceError) else "🤯"
            return self.__route_error_to_user(str(e), emoji = emoji)
        finally:
            progress_notifier.stop()

    def process_commands(self) -> CommandHandlingResult:
        try:
            result = self.__di.command_processor.execute(self.__trigger_message_text)
        except ServiceError as e:
            log.e("Command processing failed (recognized error)", e)
            message = self.__route_error_to_user(str(e), emoji = e.emoji)
            return ChatAgent.CommandHandlingResult(is_handled = True, reply = message)
        log.d(f"Command processing result is {result.status}")
        if result.status == "success":
            log.t("Command processed successfully, skipping LLM processing")
            return ChatAgent.CommandHandlingResult(is_handled = True, reply = None)
        if result.status == "failed":
            log.w("Command processing failed, replying with error message")
            message = self.__route_error_to_user(result.error_message or "Failed to process command.")
            return ChatAgent.CommandHandlingResult(is_handled = True, reply = message)
        if result.status == "ignored":
            log.t("No valid command found, continuing with normal processing")
            return ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        message = self.__route_error_to_user("Confused with processing command.")
        return ChatAgent.CommandHandlingResult(is_handled = True, reply = message)

    @classmethod
    def __remove_attachment_placeholder_content(cls, message: AIMessage) -> None:
        content = message.content
        if isinstance(content, str):
            message.content = cls.__remove_attachment_placeholder_lines(content)
            return
        if isinstance(content, list):
            cleaned_content = []
            for block in content:
                if isinstance(block, str):
                    cleaned_block = cls.__remove_attachment_placeholder_lines(block)
                    if cleaned_block:
                        cleaned_content.append(cleaned_block)
                elif isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    cleaned_block = {
                        **block,
                        "text": cls.__remove_attachment_placeholder_lines(block["text"]),
                    }
                    if cleaned_block["text"]:
                        cleaned_content.append(cleaned_block)
                else:
                    cleaned_content.append(block)
            message.content = cleaned_content

    @staticmethod
    def __remove_attachment_placeholder_lines(text: str) -> str:
        paragraphs = []
        for paragraph in text.split("\n\n"):
            lines = [
                line
                for line in paragraph.split("\n")
                if not ATTACHMENT_PLACEHOLDER_REGEX.search(line)
            ]
            cleaned_paragraph = "\n".join(lines).strip()
            if cleaned_paragraph:
                paragraphs.append(cleaned_paragraph)
        return "\n\n".join(paragraphs)

    def __is_dispatchable(self) -> bool:
        has_content = bool(self.__trigger_message_text.strip())
        chat_type = self.__di.require_invoker_chat_type()
        agent_user = resolve_agent_user(chat_type)
        invoker_handle = resolve_external_handle(self.__di.invoker, chat_type)
        agent_handle = resolve_external_handle(agent_user, chat_type)
        is_not_recursive = invoker_handle != agent_handle
        return has_content and is_not_recursive

    def __is_addressable(self) -> bool:
        chat_type = self.__di.require_invoker_chat_type()
        agent_user = resolve_agent_user(chat_type)
        agent_handle = resolve_external_handle(agent_user, chat_type)
        trigger_message_text = self.__non_quoted_text(self.__trigger_message_text)
        is_bot_mentioned = bool(agent_handle) and f"@{agent_handle}" in trigger_message_text
        return self.__di.require_invoker_chat().is_private or is_bot_mentioned

    @staticmethod
    def __non_quoted_text(text: str) -> str:
        return "\n".join(
            line
            for line in text.splitlines()
            if not line.lstrip().startswith(">>")
        )

    def __has_unanswered_bot_mention(self, agent_handle: str | None) -> bool:
        if not agent_handle:
            return False
        mention_token = f"@{agent_handle}"
        if mention_token in self.__non_quoted_text(self.__trigger_message_text):
            return True
        if config.chat_debounce_delay_s <= 0.0:
            return False
        invoker_user = self.__di.invoker
        invoker_chat = self.__di.require_invoker_chat()
        chat_type = self.__di.require_invoker_chat_type()
        agent_user = resolve_agent_user(chat_type)
        agent_user_id = agent_user.id if agent_user else None
        recent_messages = self.__di.chat_message_repo.get_latest_by_chat(
            chat_id = invoker_chat.chat_id,
            limit = config.chat_history_depth,
        )
        # walk back through recent messages from the same invoker looking for an
        # unanswered @mention. a bot reply is the only true chain-break (it means
        # the prior mention was already answered). messages from other users are
        # simply skipped — they don't answer the mention and don't break the chain.
        # known commands are self-contained — their @-tag is syntax, not conversation —
        # so we skip them rather than treating their tag as a pending mention.
        for message in recent_messages:
            if message.message_id == self.__trigger_message_id:
                continue
            if message.author_id == agent_user_id:
                return False
            if message.author_id != invoker_user.id:
                continue
            message_text = self.__non_quoted_text(message.text)
            if is_known_command(message_text, agent_handle):
                continue
            if mention_token in message_text:
                return True
        return False

    def should_reply(self) -> bool:
        chat_type = self.__di.require_invoker_chat_type()
        agent_user = resolve_agent_user(chat_type)
        agent_handle = resolve_external_handle(agent_user, chat_type)
        is_bot_mentioned = self.__has_unanswered_bot_mention(agent_handle)
        invoker_chat = self.__di.require_invoker_chat()
        if invoker_chat.reply_chance_percent == 100:
            should_reply_at_random = True
        elif invoker_chat.reply_chance_percent == 0:
            should_reply_at_random = False
        else:
            should_reply_at_random = random.randint(0, 100) <= invoker_chat.reply_chance_percent
        should_reply = (
            invoker_chat.is_private or is_bot_mentioned or should_reply_at_random
        )
        log.d(
            f"Reply decision: {'REPLYING' if should_reply else 'NOT REPLYING'}. Conditions:\n"
            f"  · is_private_chat  = {invoker_chat.is_private}\n"
            f"  · is_bot_mentioned = {is_bot_mentioned}\n"
            f"  · reply_at_random  = {should_reply_at_random}\n"
            f"  · reply_chance     = {invoker_chat.reply_chance_percent}%",
        )
        return should_reply
