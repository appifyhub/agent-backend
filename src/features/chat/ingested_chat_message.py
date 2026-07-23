from dataclasses import dataclass

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.users.user import User


@dataclass(kw_only = True)
class IngestedChatMessage:
    chat: ChatConfig
    author: User | None
    message: ChatMessage
    attachments: list[ChatAttachment]
    raw_message_text: str
