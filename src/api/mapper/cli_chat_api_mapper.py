from api.model.cli_chat_response import CliChatResponse
from api.model.cli_notify_response import CliNotifyResponse
from features.chat.config.chat_config import ChatConfig
from features.users.user import User


def domain_to_api(chat: ChatConfig) -> CliChatResponse:
    return CliChatResponse(
        chat_id = chat.chat_id.hex,
        platform = chat.chat_type.value,
        title = chat.title,
        is_private = chat.is_private,
    )


def delivery_to_api(chat: ChatConfig, user: User) -> CliNotifyResponse:
    return CliNotifyResponse(
        chat_id = chat.chat_id.hex,
        platform = chat.chat_type.value,
        title = chat.title,
        is_private = chat.is_private,
        credit_balance = user.credit_balance,
    )
