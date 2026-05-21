from uuid import UUID

from sqlalchemy.orm import Session

from db.model.chat_membership import ChatMembershipDB
from features.chat.membership.chat_membership import ChatMembership
from features.chat.membership.chat_membership_mapper import db, domain


class ChatMembershipRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, user_id: UUID, chat_id: UUID) -> ChatMembership | None:
        db_model = self._db.query(ChatMembershipDB).filter(
            ChatMembershipDB.user_id == user_id,
            ChatMembershipDB.chat_id == chat_id,
        ).first()
        return domain(db_model)

    def get_all_for_user(self, user_id: UUID) -> list[ChatMembership]:
        db_models = self._db.query(ChatMembershipDB).filter(
            ChatMembershipDB.user_id == user_id,
        ).all()
        return [domain(m) for m in db_models if m is not None]

    def get_all_for_chat(self, chat_id: UUID) -> list[ChatMembership]:
        db_models = self._db.query(ChatMembershipDB).filter(
            ChatMembershipDB.chat_id == chat_id,
        ).all()
        return [domain(m) for m in db_models if m is not None]

    def save(self, membership: ChatMembership) -> ChatMembership:
        existing = self._db.query(ChatMembershipDB).filter(
            ChatMembershipDB.user_id == membership.user_id,
            ChatMembershipDB.chat_id == membership.chat_id,
        ).first()

        if existing is not None:
            existing.is_admin = membership.is_admin
            existing.use_about_me = membership.use_about_me
            existing.use_custom_prompt = membership.use_custom_prompt
            existing.max_output_tokens = membership.max_output_tokens
            existing.max_chat_history_depth = membership.max_chat_history_depth
            existing.max_iterations = membership.max_iterations
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(membership)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(self, user_id: UUID, chat_id: UUID) -> ChatMembership | None:
        db_model = self._db.query(ChatMembershipDB).filter(
            ChatMembershipDB.user_id == user_id,
            ChatMembershipDB.chat_id == chat_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot
