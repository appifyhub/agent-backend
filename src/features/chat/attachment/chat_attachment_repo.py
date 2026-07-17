from datetime import datetime
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.model.chat_attachment import ChatAttachmentDB
from db.model.chat_message import ChatMessageDB
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_mapper import apply_to_db_model, db, domain


class ChatAttachmentRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, attachment_id: str) -> ChatAttachment | None:
        db_model = self._db.query(ChatAttachmentDB).filter(
            ChatAttachmentDB.id == attachment_id,
        ).first()
        return domain(db_model)

    def get_by_external_id(self, chat_id: UUID, external_id: str) -> ChatAttachment | None:
        db_model = self._db.query(ChatAttachmentDB).filter(
            ChatAttachmentDB.chat_id == chat_id,
            ChatAttachmentDB.external_id == external_id,
        ).first()
        return domain(db_model)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatAttachment]:
        db_models = self._db.query(ChatAttachmentDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def get_all_by_message(
        self,
        chat_id: UUID,
        message_id: str,
    ) -> list[ChatAttachment]:
        db_models = self._db.query(ChatAttachmentDB).filter(
            ChatAttachmentDB.chat_id == chat_id,
            ChatAttachmentDB.message_id == message_id,
        ).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def save(self, attachment: ChatAttachment) -> ChatAttachment:
        # identity check first
        existing: ChatAttachmentDB | None = (
            self._db.query(ChatAttachmentDB)
                .filter(ChatAttachmentDB.id == attachment.id)
                .first()
        )

        # if not found by ID, try to find by external_id
        if existing is None and attachment.external_id:
            existing = self._db.query(ChatAttachmentDB).filter(
                ChatAttachmentDB.chat_id == attachment.chat_id,
                ChatAttachmentDB.external_id == attachment.external_id,
            ).first()

        # we found an existing record, let's update
        if existing is not None:
            apply_to_db_model(attachment, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        # no existing record found, let's create a new one
        db_model = db(attachment)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(self, attachment_id: str) -> ChatAttachment | None:
        db_model = self._db.query(ChatAttachmentDB).filter(
            ChatAttachmentDB.id == attachment_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_stale(self, cutoff: datetime, only_orphans: bool = False) -> list[ChatAttachment]:
        if only_orphans:
            attachments_db = self._db.query(ChatAttachmentDB).filter(
                ChatAttachmentDB.message_id.is_(None),
                ChatAttachmentDB.created_at < cutoff,
            ).all()
        else:
            attachments_db = self._db.query(ChatAttachmentDB).join(
                ChatMessageDB,
                and_(
                    ChatMessageDB.chat_id == ChatAttachmentDB.chat_id,
                    ChatMessageDB.message_id == ChatAttachmentDB.message_id,
                ),
            ).filter(ChatMessageDB.sent_at < cutoff).all()
        deleted_attachments = []
        for attachment_db in attachments_db:
            deleted_attachments.append(domain(attachment_db))
            self._db.delete(attachment_db)
        self._db.commit()
        return deleted_attachments
