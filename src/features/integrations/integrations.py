from datetime import datetime, timedelta

from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.accounting.usage.participant_details import ParticipantInfo
from features.chat.config.chat_config import ChatConfig
from features.integrations.integration_config import (
    BACKGROUND_AGENT,
    TELEGRAM_REACTION_INITIAL_DELAY_S,
    TELEGRAM_REACTION_INTERVAL_S,
    TELEGRAM_REACTIONS,
    THE_AGENT,
    WHATSAPP_REACTION_INITIAL_DELAY_S,
    WHATSAPP_REACTION_INTERVAL_S,
    WHATSAPP_REACTIONS,
)
from features.users.user import User
from features.users.user_repo import UserRepository
from util.functions import normalize_phone_number, normalize_username

WHATSAPP_MESSAGING_WINDOW_HOURS = 24
REACTION_RESPONSE_TEMPLATE = "<reaction>{reaction}</reaction>"


def resolve_agent_user(chat_type: ChatConfigDB.ChatType) -> User:
    match chat_type:
        case ChatConfigDB.ChatType.telegram | ChatConfigDB.ChatType.whatsapp | ChatConfigDB.ChatType.github:
            return THE_AGENT
        case ChatConfigDB.ChatType.background:
            return BACKGROUND_AGENT


def resolve_external_id(user: User, chat_type: ChatConfigDB.ChatType) -> str | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return str(user.telegram_user_id) if user.telegram_user_id else None
        case ChatConfigDB.ChatType.whatsapp:
            return user.whatsapp_user_id
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return None


def resolve_external_handle(user: User, chat_type: ChatConfigDB.ChatType) -> str | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return user.telegram_username
        case ChatConfigDB.ChatType.whatsapp:
            return user.whatsapp_phone_number.get_secret_value() if user.whatsapp_phone_number else None
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return None


def format_handle(handle: str, chat_type: ChatConfigDB.ChatType) -> str:
    clean = handle.lstrip("@").lstrip("+").lstrip("#").replace(" ", "").strip()
    match chat_type:
        case ChatConfigDB.ChatType.whatsapp:
            return f"+{clean}"
        case ChatConfigDB.ChatType.telegram | ChatConfigDB.ChatType.github:
            return f"@{clean}"
        case _:
            return f"#{clean}"


def resolve_any_external_handle(user: User) -> tuple[str | None, ChatConfigDB.ChatType | None]:
    for chat_type in ChatConfigDB.ChatType:
        handle = resolve_external_handle(user, chat_type)
        if handle and handle.strip():
            return handle.strip(), chat_type
    return None, None


def resolve_user_link(user: User, chat_type: ChatConfigDB.ChatType) -> str | None:
    platform_handle = resolve_external_handle(user, chat_type)
    if not platform_handle:
        return None

    clean_handle: str
    if chat_type == ChatConfigDB.ChatType.whatsapp:
        clean_handle = str(normalize_phone_number(platform_handle)).strip()
    else:
        clean_handle = platform_handle.lstrip("@").lstrip("+").lstrip("/").strip()
    if not clean_handle:
        return None

    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return f"[@{clean_handle}](https://t.me/{clean_handle})"
        case ChatConfigDB.ChatType.whatsapp:
            return f"[{clean_handle}](https://wa.me/{clean_handle})"
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return f"[@{clean_handle}](https://github.com/{clean_handle})"


def resolve_private_chat_id(user: User, chat_type: ChatConfigDB.ChatType) -> str | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return user.telegram_chat_id
        case ChatConfigDB.ChatType.whatsapp:
            return user.whatsapp_user_id
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return None


def resolve_user_to_create(handle: str, chat_type: ChatConfigDB.ChatType) -> User | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            normalized_username = (normalize_username(handle) or "").strip()
            return User(
                full_name = None,
                telegram_username = normalized_username,
                telegram_chat_id = None,
                telegram_user_id = None,
                group = UserDB.Group.standard,
            )
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return None
        case ChatConfigDB.ChatType.whatsapp:
            normalized_phone = (normalize_phone_number(handle) or "").strip()
            return User(
                full_name = None,
                whatsapp_user_id = normalized_phone,
                whatsapp_phone_number = SecretStr(normalized_phone),
                group = UserDB.Group.standard,
            )


def user_to_participant(user: User) -> ParticipantInfo:
    handle, chat_type = resolve_any_external_handle(user)
    platform = chat_type.value if chat_type else None
    return ParticipantInfo(
        user_id = user.id,
        full_name = user.full_name,
        platform = platform,
        handle = handle,
    )


def is_the_agent(who: User | None, chat_type: ChatConfigDB.ChatType) -> bool:
    if not who:
        return False
    agent_user = resolve_agent_user(chat_type)
    user_id = resolve_external_id(who, chat_type)
    agent_id = resolve_external_id(agent_user, chat_type)
    return user_id is not None and user_id == agent_id


def is_own_chat(chat_config: ChatConfig, user: User) -> bool:
    match chat_config.chat_type:
        case ChatConfigDB.ChatType.telegram:
            is_own_chat_configured = (user.telegram_chat_id is not None) and (chat_config.external_id is not None)
            return chat_config.is_private and is_own_chat_configured and user.telegram_chat_id == chat_config.external_id
        case ChatConfigDB.ChatType.whatsapp:
            is_own_chat_configured = (user.whatsapp_user_id is not None) and (chat_config.external_id is not None)
            normalized_user_id = normalize_phone_number(user.whatsapp_user_id) or ""
            normalized_external_id = normalize_phone_number(chat_config.external_id) or ""
            return chat_config.is_private and is_own_chat_configured and normalized_user_id == normalized_external_id
        case ChatConfigDB.ChatType.background:
            return False
        case ChatConfigDB.ChatType.github:
            return False


def lookup_user_by_handle(handle: str, chat_type: ChatConfigDB.ChatType, user_repo: UserRepository) -> User | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            normalized_username = (normalize_username(handle) or "").strip()
            return user_repo.get_by_telegram_username(normalized_username)
        case ChatConfigDB.ChatType.whatsapp:
            normalized_phone = (normalize_phone_number(handle) or "").strip()
            # Try by whatsapp_user_id first (not encrypted, faster), then fall back to phone number
            user = user_repo.get_by_whatsapp_user_id(normalized_phone)
            if not user:
                user = user_repo.get_by_whatsapp_phone_number(normalized_phone)
            return user
        case ChatConfigDB.ChatType.background:
            return None
        case ChatConfigDB.ChatType.github:
            return None


def add_messaging_frequency_warning(response_data: dict, chat_type: ChatConfigDB.ChatType | None) -> None:
    if chat_type == ChatConfigDB.ChatType.whatsapp:
        response_data["warning"] = (
            "WhatsApp's 24-hour messaging window: Notifications will only be delivered if "
            "you've messaged the agent within the last 24 hours. If you haven't sent a message "
            "recently, you won't receive this alert notification."
        )


def resolve_allowed_reactions(chat_type: ChatConfigDB.ChatType) -> list[str]:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return TELEGRAM_REACTIONS
        case ChatConfigDB.ChatType.whatsapp:
            return WHATSAPP_REACTIONS
        case _:
            return []


def is_reaction_response(text: str, chat_type: ChatConfigDB.ChatType) -> bool:
    return text.strip() in resolve_allowed_reactions(chat_type)


def format_reaction_response(reaction: str) -> str:
    return REACTION_RESPONSE_TEMPLATE.format(reaction = reaction)


def resolve_reaction_timing(chat_type: ChatConfigDB.ChatType) -> tuple[int, int] | None:
    match chat_type:
        case ChatConfigDB.ChatType.telegram:
            return TELEGRAM_REACTION_INITIAL_DELAY_S, TELEGRAM_REACTION_INTERVAL_S
        case ChatConfigDB.ChatType.whatsapp:
            return WHATSAPP_REACTION_INITIAL_DELAY_S, WHATSAPP_REACTION_INTERVAL_S
        case _:
            return None


def resolve_best_notification_chat(user: User, di: DI) -> ChatConfig | None:
    telegram_chat = _find_private_chat(user, ChatConfigDB.ChatType.telegram, di)
    whatsapp_chat = _find_private_chat(user, ChatConfigDB.ChatType.whatsapp, di)

    telegram_time = _get_last_user_message_time(telegram_chat, user, di) if telegram_chat else None
    whatsapp_time = _get_last_user_message_time(whatsapp_chat, user, di) if whatsapp_chat else None

    is_whatsapp_eligible = (
        whatsapp_chat is not None
        and whatsapp_time is not None
        and (datetime.now() - whatsapp_time) < timedelta(hours = WHATSAPP_MESSAGING_WINDOW_HOURS)
    )

    if is_whatsapp_eligible and telegram_chat is not None and telegram_time is not None:
        return whatsapp_chat if whatsapp_time > telegram_time else telegram_chat
    if is_whatsapp_eligible:
        return whatsapp_chat
    if telegram_chat is not None:
        return telegram_chat
    return None


def _find_private_chat(user: User, chat_type: ChatConfigDB.ChatType, di: DI) -> ChatConfig | None:
    external_id = resolve_external_id(user, chat_type)
    if not external_id:
        return None
    chat = di.chat_config_repo.get_by_external_identifiers(external_id, chat_type)
    if not chat:
        return None
    return chat if chat.is_private else None


def _get_last_user_message_time(chat: ChatConfig, user: User, di: DI) -> datetime | None:
    messages = di.chat_message_repo.get_latest_by_chat(chat.chat_id, limit = 30)
    for message in messages:
        if message.author_id == user.id:
            return message.sent_at
    return None
