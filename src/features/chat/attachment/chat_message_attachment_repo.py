from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from db.model.chat_message import ChatMessageDB
from db.model.chat_message_attachment import ChatMessageAttachmentDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_mapper import db, domain


class ChatMessageAttachmentRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, attachment_id: str) -> ChatMessageAttachment | None:
        db_model = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.id == attachment_id,
        ).first()
        return domain(db_model)

    def get_by_external_id(self, external_id: str) -> ChatMessageAttachment | None:
        db_model = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.external_id == external_id,
        ).first()
        return domain(db_model)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatMessageAttachment]:
        db_models = self._db.query(ChatMessageAttachmentDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def get_all_by_message(
        self,
        chat_id: UUID,
        message_id: str,
    ) -> list[ChatMessageAttachment]:
        db_models = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.chat_id == chat_id,
            ChatMessageAttachmentDB.message_id == message_id,
        ).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def save(self, attachment: ChatMessageAttachment) -> ChatMessageAttachment:
        existing: ChatMessageAttachmentDB | None = None
        if attachment.id is not None:
            existing = self._db.query(ChatMessageAttachmentDB).filter(
                ChatMessageAttachmentDB.id == attachment.id,
            ).first()

        if existing is not None:
            self.__copy_to_db_model(attachment, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(attachment)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(self, attachment_id: str) -> ChatMessageAttachment | None:
        db_model = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.id == attachment_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_by_old_messages(self, cutoff: datetime) -> int:
        old_message_pairs = select(ChatMessageDB.chat_id, ChatMessageDB.message_id).where(
            ChatMessageDB.sent_at < cutoff,
        )
        deleted_count = self._db.query(ChatMessageAttachmentDB).filter(
            tuple_(
                ChatMessageAttachmentDB.chat_id,
                ChatMessageAttachmentDB.message_id,
            ).in_(old_message_pairs),
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def __copy_to_db_model(
        self,
        source: ChatMessageAttachment,
        target: ChatMessageAttachmentDB,
    ) -> None:
        target.external_id = source.external_id
        target.chat_id = source.chat_id
        target.message_id = source.message_id
        target.size = source.size
        target.last_url = source.last_url
        target.last_url_until = source.last_url_until
        target.extension = source.extension
        target.mime_type = source.mime_type
