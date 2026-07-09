from datetime import datetime
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.model.chat_message import ChatMessageDB
from db.model.chat_message_attachment import ChatMessageAttachmentDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_mapper import apply_to_db_model, db, domain

PREFIX_OUTGOING = "outgoing-"
PREFIX_EXTERNAL = "external-"


class ChatMessageAttachmentRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, attachment_id: str) -> ChatMessageAttachment | None:
        db_model = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.id == attachment_id,
        ).first()
        return domain(db_model)

    def get_by_external_id(self, chat_id: UUID, external_id: str) -> ChatMessageAttachment | None:
        db_model = self._db.query(ChatMessageAttachmentDB).filter(
            ChatMessageAttachmentDB.chat_id == chat_id,
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
        # identity check first
        existing: ChatMessageAttachmentDB | None = (
            self._db.query(ChatMessageAttachmentDB)
                .filter(ChatMessageAttachmentDB.id == attachment.id)
                .first()
        )

        # if not found by ID, try to find by external_id
        if existing is None and attachment.external_id:
            existing = self._db.query(ChatMessageAttachmentDB).filter(
                ChatMessageAttachmentDB.chat_id == attachment.chat_id,
                ChatMessageAttachmentDB.external_id == attachment.external_id,
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

    def delete_stale(self, cutoff: datetime, only_orphans: bool = False) -> list[ChatMessageAttachment]:
        if only_orphans:
            attachments_db = self._db.query(ChatMessageAttachmentDB).filter(
                ChatMessageAttachmentDB.message_id.is_(None),
                ChatMessageAttachmentDB.created_at < cutoff,
            ).all()
        else:
            attachments_db = self._db.query(ChatMessageAttachmentDB).join(
                ChatMessageDB,
                and_(
                    ChatMessageDB.chat_id == ChatMessageAttachmentDB.chat_id,
                    ChatMessageDB.message_id == ChatMessageAttachmentDB.message_id,
                ),
            ).filter(ChatMessageDB.sent_at < cutoff).all()
        deleted_attachments = []
        for attachment_db in attachments_db:
            deleted_attachments.append(domain(attachment_db))
            self._db.delete(attachment_db)
        self._db.commit()
        return deleted_attachments
