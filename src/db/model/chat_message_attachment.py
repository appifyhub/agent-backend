from sqlalchemy import Column, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from db.model.base import BaseModel
from util.functions import generate_short_uuid


class ChatMessageAttachmentDB(BaseModel):
    __tablename__ = "chat_message_attachments"

    id = Column(String, primary_key = True, default = generate_short_uuid)
    external_id = Column(String, nullable = True)
    chat_id = Column(UUID(as_uuid = True), nullable = False)
    message_id = Column(String, nullable = False)
    size = Column(Integer, nullable = True)
    last_url = Column(String, nullable = True)
    last_url_until = Column(Integer, nullable = True)
    extension = Column(String, nullable = True)
    mime_type = Column(String, nullable = True)

    __table_args__ = (
        PrimaryKeyConstraint(id, name = "pk_chat_message_attachments"),
        ForeignKeyConstraint(
            [chat_id, message_id],
            ["chat_messages.chat_id", "chat_messages.message_id"],
            name = "chat_message_attachments_message_fkey",
        ),
        Index("idx_external_id", external_id),
    )
