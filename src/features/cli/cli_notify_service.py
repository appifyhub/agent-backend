from dataclasses import dataclass
from typing import cast
from uuid import UUID

from requests import RequestException

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.integrations.integration_config import CLI_NOTIFICATION_PLATFORMS, TEXT_MESSAGE_LIMITS
from features.integrations.integrations import (
    find_private_chat,
    measure_text_message_length,
    resolve_best_notification_chat,
    resolve_external_handle,
    resolve_external_id,
    resolve_text_message_limit,
)
from features.users.user import User
from util import log
from util.error_codes import (
    INVALID_NOTIFICATION_MESSAGE,
    INVALID_PLATFORM,
    NO_PRIVATE_CHAT,
    NOTIFICATION_DELIVERY_FAILED,
)
from util.errors import AuthorizationError, ExternalServiceError, ValidationError


class CliNotifyService:

    @dataclass(frozen = True)
    class Delivery:
        chat: ChatConfig
        user: User

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def notify_invoker(self, hostname: str, message: str, platform: str | None) -> Delivery:
        self.__di.authorization_service.require_user_is_chat_ready(self.__di.invoker)
        text = self.__validate_message(message)
        chat = self.__resolve_private_chat(platform)
        return self.__deliver(hostname, chat, text)

    def notify_chat(self, hostname: str, chat_id: str | UUID, message: str) -> Delivery:
        self.__di.authorization_service.require_user_is_chat_ready(self.__di.invoker)
        text = self.__validate_message(message)
        chat = self.__di.authorization_service.validate_chat_admin(self.__di.invoker, chat_id)
        return self.__deliver(hostname, chat, text)

    # noinspection PyMethodMayBeStatic
    def __validate_message(self, message: str) -> str:
        text = message.strip()
        max_length = min(TEXT_MESSAGE_LIMITS.values())
        if not text or len(text) > max_length:
            raise ValidationError(f"Message must have 1 to {max_length} characters", INVALID_NOTIFICATION_MESSAGE)
        return text

    def __resolve_private_chat(self, platform: str | None) -> ChatConfig:
        # platform is specified exactly, let's try to find that chat first
        if platform is not None:
            chat_type = ChatConfigDB.ChatType.lookup(platform)
            if chat_type not in CLI_NOTIFICATION_PLATFORMS:
                raise ValidationError(f"Unsupported platform: {platform}", INVALID_PLATFORM)
            platform_chat = find_private_chat(self.__di.invoker, chat_type, self.__di)
            if platform_chat is None:
                raise AuthorizationError(f"No private {platform} chat is available", NO_PRIVATE_CHAT)
            return platform_chat

        # platform is not specified, let's do the best effort
        best_chat = resolve_best_notification_chat(self.__di.invoker, self.__di)
        if best_chat is not None:
            return best_chat
        raise AuthorizationError("No private chat is available", NO_PRIVATE_CHAT)

    def __deliver(self, hostname: str, chat: ChatConfig, text: str) -> Delivery:
        final_text = self.__compose_text(hostname, chat, text)
        self.__di.spending_service.validate_message_delivery_pre_flight(chat, self.__di.invoker.id)
        self.__di.rollback_db_session()
        chat_di = self.__di.clone(invoker_chat_id = chat.chat_id.hex)
        try:
            chat_di.platform_bot_sdk().send_text_message(str(chat.external_id), final_text)
        except RequestException as e:
            raise ExternalServiceError("The platform could not deliver the message", NOTIFICATION_DELIVERY_FAILED) from e
        owner = cast(User, self.__di.user_repo.get(self.__di.invoker.id))  # because credits change
        log.i(f"CLI notification delivered by user '{owner.id.hex}' to chat '{chat.chat_id.hex}'")
        return CliNotifyService.Delivery(chat = chat, user = owner)

    def __compose_text(self, hostname: str, chat: ChatConfig, text: str) -> str:
        identity = resolve_external_handle(self.__di.invoker, chat.chat_type) or resolve_external_id(self.__di.invoker, chat.chat_type)  # ruff: ignore[line-too-long]
        prefix = f"🖥️  [{identity}@{hostname}] "
        limit = resolve_text_message_limit(chat.chat_type)
        full_text = prefix + text
        if limit is None or measure_text_message_length(full_text, chat.chat_type) <= limit:
            return full_text

        # if the message is too long, we need to trim it from the back
        longest_head = 0
        low, high = 0, len(text) - 1
        while low <= high:
            candidate = (low + high) // 2
            truncated = prefix + text[:candidate].rstrip() + "…"
            if measure_text_message_length(truncated, chat.chat_type) <= limit:
                longest_head = candidate
                low = candidate + 1
            else:
                high = candidate - 1
        return prefix + text[:longest_head].rstrip() + "…"
