import random
import re
from datetime import datetime
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.integrations.integrations import is_the_agent, resolve_agent_user, resolve_external_handle, resolve_external_id
from features.prompting.prompt_library import CHAT_MESSAGE_DELIMITER
from features.users.user import User
from util import log

_CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s")
_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s")


def _is_list_item(line: str) -> bool:
    return bool(_UNORDERED_LIST_RE.match(line) or _ORDERED_LIST_RE.match(line))


def _unclosed_fence_marker(text: str) -> str | None:
    open_fence = None
    for line in text.split("\n"):
        match = _CODE_FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if open_fence is None:
                open_fence = marker
            elif marker[0] == open_fence[0]:
                open_fence = None
    return open_fence


def _is_in_code_block(text: str) -> bool:
    return _unclosed_fence_marker(text) is not None


def _ends_in_list_context(text: str) -> bool:
    for line in reversed(text.split("\n")):
        if not line.strip():
            continue
        if _is_list_item(line):
            return True
        if line.startswith(("  ", "\t")):
            continue
        return False
    return False


def _starts_with_list_item(text: str) -> bool:
    for line in text.split("\n"):
        if line.strip():
            return _is_list_item(line)
    return False


def _split_preserving_blocks(content: str, delimiter: str) -> list[str]:
    parts = content.split(delimiter)
    if len(parts) <= 1:
        return parts

    result = []
    current = parts[0]

    for part in parts[1:]:
        if _is_in_code_block(current) or (
            _ends_in_list_context(current) and _starts_with_list_item(part)
        ):
            current += delimiter + part
        else:
            result.append(current)
            current = part

    result.append(current)
    return result


class DomainLangchainMapper:

    def map_to_langchain(
        self,
        author: User | None,
        message: ChatMessage,
        chat_type: ChatConfigDB.ChatType,
    ) -> HumanMessage | AIMessage:
        log.t(f"Mapping {message.message_id} by {author.id.hex if author else '<unknown>'} to Langchain message")
        content = self.__map_stored_message_text(author, message, chat_type)
        if not author or is_the_agent(author, chat_type):
            return AIMessage(content)
        return HumanMessage(content)

    def map_bot_message_to_storage(self, chat: ChatConfig, message: AIMessage) -> list[ChatMessage]:
        log.t(f"Mapping AI message '{message}' to storage message")
        result: list[ChatMessage] = []
        content = self.__map_bot_message_text(message)
        parts = _split_preserving_blocks(content, CHAT_MESSAGE_DELIMITER)
        for part in parts:
            if not part:
                continue
            if fence := _unclosed_fence_marker(part):
                part += f"\n{fence}"
            sent_at = datetime.now()
            agent_user = resolve_agent_user(chat.chat_type)
            storage_message = ChatMessage(
                chat_id = chat.chat_id,
                message_id = DomainLangchainMapper.__construct_bot_message_id(chat.chat_id, sent_at),  # unused outside
                author_id = agent_user.id,
                sent_at = sent_at,
                text = part,
            )
            result.append(storage_message)
        return result

    # noinspection PyMethodMayBeStatic
    def __map_stored_message_text(self, author: User | None, message: ChatMessage, chat_type: ChatConfigDB.ChatType) -> str:
        parts = []
        if author:
            name_parts = []
            if platform_handle := resolve_external_handle(author, chat_type):
                name_parts.append(f"@{platform_handle}")
            if author.full_name:
                name_parts.append(f"[{author.full_name}]")
            if not name_parts and (platform_user_id := resolve_external_id(author, chat_type)):
                name_parts.append(f"#UID-{platform_user_id}")
            if not is_the_agent(author, chat_type):
                name_tag = " ".join(name_parts)
                parts.append(f"{name_tag}:")
        parts.append(message.text)
        log.t(f"  Mapped message parts: {parts}, joining...")
        return "\n".join(parts)

    # noinspection PyMethodMayBeStatic
    def __map_bot_message_text(self, message: AIMessage) -> str:
        log.t(f"  Mapping AI message {message}")

        def pretty_print(raw_dict):
            return "\n".join(f"{key}: {value}" for key, value in raw_dict.items())

        def extract_text_from_dict(item: dict) -> str:
            # Handle LangChain content block format: {'type': 'text', 'text': '...', ...}
            if item.get("type") == "thinking":
                thinking = item.get("thinking", "")
                return DomainLangchainMapper._format_thinking(thinking) if thinking else ""
            if item.get("type") == "redacted_thinking":
                return ""
            if "text" in item:
                return item["text"]
            # Fallback to pretty print for other dict formats
            return pretty_print(item)

        # edge: no content
        if not message.content:
            return ""
        # main: plain string
        if isinstance(message.content, str):
            return message.content
        # edge: it's a dict
        if isinstance(message.content, dict):
            return extract_text_from_dict(message.content)
        # edge: it's a list
        if isinstance(message.content, list):
            messages: list[str] = []
            for item in message.content:
                if isinstance(item, str):
                    messages.append(item)
                elif isinstance(item, dict):
                    messages.append(extract_text_from_dict(item))
                else:
                    messages.append(str(item))
            return CHAT_MESSAGE_DELIMITER.join(m for m in messages if m)
        # noinspection PyUnreachableCode
        return str(message.content)

    @staticmethod
    def _format_thinking(thinking: str) -> str:
        lines = "\n".join(f"> {line}" for line in thinking.splitlines())
        return f"💭\n{lines}"

    @staticmethod
    def __construct_bot_message_id(chat_id: UUID, sent_at: datetime) -> str:
        random_seed = str(random.randint(1000, 9999))
        formatted_time = sent_at.strftime("%y%m%d%H%M%S")
        result = f"{chat_id}-{formatted_time}-{random_seed}"
        return result
