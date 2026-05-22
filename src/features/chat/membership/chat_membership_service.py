from uuid import UUID

from db.schema.chat_config import ChatConfig
from db.schema.user import User
from di.di import DI
from features.chat.membership.chat_membership import ChatMembership
from features.integrations.platform_bot_sdk import ChatAccess
from util import log
from util.error_codes import NOT_CHAT_MEMBER
from util.errors import AuthorizationError


class ChatMembershipService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def sync(self, user: User, chat: ChatConfig) -> ChatMembership:
        existing = self.__di.chat_membership_repo.get(user.id, chat.chat_id)
        access = self.__di.platform_bot_sdk().resolve_chat_access(chat, user)
        if existing is None and access is None:
            raise AuthorizationError(
                f"User '{user.id.hex}' is not a participant of chat '{chat.chat_id.hex}'",
                NOT_CHAT_MEMBER,
            )
        is_admin = access in (ChatAccess.owner, ChatAccess.admin)
        if existing is None:
            log.t(f"  Creating membership for user '{user.id.hex}' in chat '{chat.chat_id.hex}'")
            return self.__di.chat_membership_repo.save(
                ChatMembership(
                    user_id = user.id,
                    chat_id = chat.chat_id,
                    is_admin = is_admin,
                    use_about_me = True,
                    use_custom_prompt = True,
                ),
            )
        if existing.is_admin != is_admin:
            return self.__di.chat_membership_repo.save(
                ChatMembership(
                    user_id = user.id,
                    chat_id = chat.chat_id,
                    is_admin = is_admin,
                    use_about_me = existing.use_about_me,
                    use_custom_prompt = existing.use_custom_prompt,
                    max_output_tokens = existing.max_output_tokens,
                    max_chat_history_depth = existing.max_chat_history_depth,
                    max_iterations = existing.max_iterations,
                ),
            )
        return existing

    def get(self, user_id: UUID, chat_id: UUID) -> ChatMembership | None:
        return self.__di.chat_membership_repo.get(user_id, chat_id)

    def get_all_for_user(self, user_id: UUID) -> list[ChatMembership]:
        return self.__di.chat_membership_repo.get_all_for_user(user_id)

    def save(self, membership: ChatMembership) -> ChatMembership:
        return self.__di.chat_membership_repo.save(membership)

    def refresh_chat_memberships(self, user: User, current_admin_chats: list[ChatConfig]) -> list[ChatMembership]:
        admin_chat_ids: set[UUID] = {chat.chat_id for chat in current_admin_chats}
        existing_memberships = self.__di.chat_membership_repo.get_all_for_user(user.id)
        existing_by_chat_id = {m.chat_id: m for m in existing_memberships}

        for chat_id in admin_chat_ids:
            existing = existing_by_chat_id.get(chat_id)
            if existing is None:
                self.__di.chat_membership_repo.save(
                    ChatMembership(
                        user_id = user.id,
                        chat_id = chat_id,
                        is_admin = True,
                        use_about_me = True,
                        use_custom_prompt = True,
                    ),
                )
            elif not existing.is_admin:
                self.__di.chat_membership_repo.save(
                    ChatMembership(
                        user_id = user.id,
                        chat_id = chat_id,
                        is_admin = True,
                        use_about_me = existing.use_about_me,
                        use_custom_prompt = existing.use_custom_prompt,
                        max_output_tokens = existing.max_output_tokens,
                        max_chat_history_depth = existing.max_chat_history_depth,
                        max_iterations = existing.max_iterations,
                    ),
                )

        for chat_id, existing in existing_by_chat_id.items():
            if existing.is_admin and chat_id not in admin_chat_ids:
                self.__di.chat_membership_repo.save(
                    ChatMembership(
                        user_id = user.id,
                        chat_id = chat_id,
                        is_admin = False,
                        use_about_me = existing.use_about_me,
                        use_custom_prompt = existing.use_custom_prompt,
                        max_output_tokens = existing.max_output_tokens,
                        max_chat_history_depth = existing.max_chat_history_depth,
                        max_iterations = existing.max_iterations,
                    ),
                )

        return self.__di.chat_membership_repo.get_all_for_user(user.id)
