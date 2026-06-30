from uuid import UUID

from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership
from features.integrations.platform_bot_sdk import ChatAccess
from features.users.user import User
from util import log
from util.config import config
from util.error_codes import (
    CHAT_NOT_FOUND,
    MALFORMED_CHAT_ID,
    MALFORMED_USER_ID,
    NOT_CHAT_ADMIN,
    NOT_TARGET_USER,
    USER_NOT_FOUND,
    WAITLIST_ACCOUNT_NOT_ACTIVE,
    WAITLIST_INVITED_POLICIES_REQUIRED,
)
from util.errors import AuthorizationError, NotFoundError, ValidationError


class AuthorizationService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_chat(self, chat: str | UUID | ChatConfig) -> ChatConfig:
        if isinstance(chat, ChatConfig):
            return chat

        log.d(f"Validating chat data for '{chat}'")
        try:
            chat_uuid = chat if isinstance(chat, UUID) else UUID(hex = chat)
        except ValueError as e:
            raise ValidationError(f"Malformed chat ID '{chat}'", MALFORMED_CHAT_ID) from e
        chat_config = self.__di.chat_config_repo.get(chat_uuid)
        if not chat_config:
            raise NotFoundError(f"Chat '{chat}' not found", CHAT_NOT_FOUND)
        return chat_config

    def validate_user(self, user: str | UUID | User) -> User:
        if isinstance(user, User):
            return user

        try:
            user_uuid = user if isinstance(user, UUID) else UUID(hex = user)
        except ValueError as e:
            raise ValidationError(f"Malformed user ID '{user}'", MALFORMED_USER_ID) from e
        validated_user = self.__di.user_repo.get(user_uuid)
        if not validated_user:
            raise NotFoundError(f"User '{user}' not found", USER_NOT_FOUND)
        return validated_user

    def get_authorized_chats(self, user: str | UUID | User) -> list[ChatConfig]:
        user = self.validate_user(user)
        log.d(f"Getting administered chats for user {user.id.hex}")

        log.t("  Validating chat configurations")
        max_chats = config.max_users * 10  # assuming each user administers 10 chats
        all_chat_configs = self.__di.chat_config_repo.get_all(limit = max_chats)
        if not all_chat_configs:
            log.t("  No chat configurations found in DB")
            return []
        log.t(f"  Found {len(all_chat_configs)} chat configurations to check")

        log.t("  Checking admin status in each chat")
        administered_chats: list[ChatConfig] = []
        for chat_config in all_chat_configs:
            log.t(f"    Checking {chat_config.chat_type.value} chat: {chat_config.title} ({chat_config.chat_id})")
            try:
                access = self.__di.platform_bot_sdk().resolve_chat_access(chat_config, user)
                if access in (ChatAccess.owner, ChatAccess.admin):
                    log.t(f"    User {user.id.hex} is admin for chat {chat_config.chat_id}")
                    administered_chats.append(chat_config)
                else:
                    log.t(f"    User {user.id.hex} is not admin for chat {chat_config.chat_id}")
            except Exception as e:
                log.t(f"    Error checking admin status for '{chat_config.chat_id}'", e)

        log.t("  Sorting administered chats now")
        administered_chats.sort(
            key = lambda chat: (
                not chat.is_private,
                chat.chat_type.value,
                chat.title.lower() if chat.title else "",
                chat.external_id or "",
                chat.chat_id.hex,
            ),
        )
        log.i(f"  Found {len(administered_chats)} administered chats")
        return administered_chats

    def validate_chat_admin(
        self,
        invoker_user: str | UUID | User,
        target_chat: str | UUID | ChatConfig,
    ) -> ChatConfig:
        invoker_user = self.validate_user(invoker_user)
        chat_config = self.validate_chat(target_chat)
        log.d(f"Validating admin rights for user '{invoker_user.id.hex}' in chat '{chat_config.chat_id.hex}'")
        membership = self.__di.chat_membership_service.sync(invoker_user, chat_config)
        if not membership.is_admin:
            raise AuthorizationError(
                f"User '{invoker_user.id.hex}' is not admin in '{chat_config.title}'",
                NOT_CHAT_ADMIN,
            )
        return chat_config

    def update_chat_authorization(
        self,
        user: str | UUID | User,
        chat: str | UUID | ChatConfig,
    ) -> ChatMembership:
        user = self.validate_user(user)
        chat_config = self.validate_chat(chat)
        log.d(f"Updating chat authorization for user '{user.id.hex}' in chat '{chat_config.chat_id.hex}'")
        return self.__di.chat_membership_service.sync(user, chat_config)

    def update_all_chat_authorizations(self, user: str | UUID | User) -> list[ChatMembership]:
        user = self.validate_user(user)
        log.d(f"Updating all chat authorizations for user '{user.id.hex}'")
        current_admin_chats = self.get_authorized_chats(user)
        return self.__di.chat_membership_service.refresh_chat_memberships(user, current_admin_chats)

    def authorize_for_user(self, invoker_user: str | UUID | User, target_user: str | UUID | User) -> User:
        invoker_user = self.validate_user(invoker_user)
        target_user = self.validate_user(target_user)
        log.d(f"Authorizing user '{invoker_user.id.hex}' to access user '{target_user.id.hex}'")
        if invoker_user.id != target_user.id:
            raise AuthorizationError(f"Target user '{target_user.id.hex}' is not the allowed user '{invoker_user.id.hex}'", NOT_TARGET_USER)  # noqa: E501
        return target_user

    def require_user_is_chat_ready(self, user: str | UUID | User) -> User:
        user = self.validate_user(user)
        if user.is_on_waitlist:
            if user.is_invited_to_start and not user.are_policies_accepted:
                raise AuthorizationError(
                    "You're invited to start. Accept policies in /settings first.",
                    WAITLIST_INVITED_POLICIES_REQUIRED,
                )
            if user.is_invited_to_start and user.are_policies_accepted:
                log.w(
                    f"Contradictory onboarding state for user #{user.id.hex}: "
                    "waitlisted and invited, but policies accepted.",
                )
            raise AuthorizationError(
                "Access is currently limited. The waitlist is not open yet, so your account is still pending.",
                WAITLIST_ACCOUNT_NOT_ACTIVE,
            )

        if not user.are_policies_accepted:
            raise AuthorizationError("Accept policies in /settings first.", WAITLIST_INVITED_POLICIES_REQUIRED)
        return user

    def require_waitlisted_user_can_activate(self, user: str | UUID | User) -> User:
        user = self.validate_user(user)
        if not user.is_on_waitlist:
            return user

        has_available_capacity = self.__di.user_repo.count() < config.max_users
        if (not user.is_invited_to_start) and (not has_available_capacity):
            raise AuthorizationError(
                "Activation is not available right now because maximum user capacity has been reached. "
                "Your account remains on the waitlist.",
                WAITLIST_ACCOUNT_NOT_ACTIVE,
            )
        return user
