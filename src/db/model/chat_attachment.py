from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.model.base import BaseModel
from util.functions import generate_short_uuid


class ChatAttachmentDB(BaseModel):
    __tablename__ = "chat_attachments"

    id = Column(String, primary_key = True, default = generate_short_uuid)
    external_id = Column(String, nullable = True)
    chat_id = Column(UUID(as_uuid = True), nullable = False)
    message_id = Column(String, nullable = True)
    uploader_user_id = Column(UUID(as_uuid = True), nullable = False)
    created_at = Column(DateTime, default = func.now(), nullable = False)
    size = Column(Integer, nullable = True)
    last_url = Column(String, nullable = True)
    extension = Column(String, nullable = True)
    mime_type = Column(String, nullable = True)

    __table_args__ = (
        PrimaryKeyConstraint(id, name = "pk_chat_attachments"),
        ForeignKeyConstraint(
            [chat_id],
            ["chat_configs.chat_id"],
            name = "chat_attachments_chat_id_fkey",
        ),
        ForeignKeyConstraint(
            [uploader_user_id],
            ["simulants.id"],
            name = "chat_attachments_uploader_user_id_fkey",
        ),
        UniqueConstraint(chat_id, external_id, name = "uq_attachment_external_per_chat"),
    )
