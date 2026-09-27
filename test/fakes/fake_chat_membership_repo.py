from dataclasses import replace
from uuid import UUID

from features.chat.membership.chat_membership import ChatMembership


class FakeChatMembershipRepository:

    _memberships: dict[tuple[UUID, UUID], ChatMembership]

    def __init__(self):
        self._memberships = {}

    def get(self, user_id: UUID, chat_id: UUID) -> ChatMembership | None:
        membership = self._memberships.get((user_id, chat_id))
        return replace(membership) if membership is not None else None

    def get_all_for_user(self, user_id: UUID) -> list[ChatMembership]:
        return [replace(m) for m in self._memberships.values() if m.user_id == user_id]

    def save(self, membership: ChatMembership) -> ChatMembership:
        self._memberships[(membership.user_id, membership.chat_id)] = replace(membership)
        return replace(membership)
