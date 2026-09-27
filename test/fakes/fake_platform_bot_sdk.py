from uuid import UUID

from features.chat.config.chat_config import ChatConfig
from features.integrations.platform_bot_sdk import ChatAccess
from features.users.user import User
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakePlatformBotSDK:

    access: dict[tuple[UUID, UUID], ChatAccess | Exception | None]

    def __init__(self):
        self.access = {}

    def resolve_chat_access(self, chat: ChatConfig, user: User) -> ChatAccess | None:
        key = (user.id, chat.chat_id)
        if key not in self.access:
            raise InternalError(f"No platform access configured for user/chat {key}", DI_DEPENDENCY_NOT_MET)
        access = self.access[key]
        if isinstance(access, Exception):
            raise access
        return access
