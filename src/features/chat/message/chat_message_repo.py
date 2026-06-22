from datetime import datetime
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.model.chat_message import ChatMessageDB
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_mapper import db, domain


class ChatMessageRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(
        self,
        chat_id: UUID,
        message_id: str,
    ) -> ChatMessage | None:
        db_model = self._db.query(ChatMessageDB).filter(
            ChatMessageDB.chat_id == chat_id,
            ChatMessageDB.message_id == message_id,
        ).first()
        return domain(db_model)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatMessage]:
        db_models = self._db.query(ChatMessageDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def get_latest_by_chat(
        self,
        chat_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatMessage]:
        db_models = (
            self._db.query(ChatMessageDB).filter(
                ChatMessageDB.chat_id == chat_id,
            )
            .order_by(desc(ChatMessageDB.sent_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def save(self, message: ChatMessage) -> ChatMessage:
        existing = self._db.query(ChatMessageDB).filter(
            ChatMessageDB.chat_id == message.chat_id,
            ChatMessageDB.message_id == message.message_id,
        ).first()

        if existing is not None:
            self.__copy_to_db_model(message, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(message)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(
        self,
        chat_id: UUID,
        message_id: str,
    ) -> ChatMessage | None:
        db_model = self._db.query(ChatMessageDB).filter(
            ChatMessageDB.chat_id == chat_id,
            ChatMessageDB.message_id == message_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_older_than(self, cutoff: datetime) -> int:
        deleted_count = self._db.query(ChatMessageDB).filter(
            ChatMessageDB.sent_at < cutoff,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def __copy_to_db_model(
        self,
        source: ChatMessage,
        target: ChatMessageDB,
    ) -> None:
        target.author_id = source.author_id
        target.sent_at = source.sent_at
        target.text = source.text
