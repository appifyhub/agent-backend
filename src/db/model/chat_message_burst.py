from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID

from db.model.base import BaseModel


class ChatMessageBurstDB(BaseModel):
    __tablename__ = "chat_message_bursts"

    chat_id = Column(UUID(as_uuid = True), nullable = False)
    author_id = Column(UUID(as_uuid = True), nullable = False)
    message_count = Column(BigInteger, nullable = False)
    process_after = Column(DateTime, nullable = False)
    last_message_sent_at = Column(DateTime, nullable = False)
    last_message_ingestion_order = Column(BigInteger, nullable = False)
    is_addressed = Column(Boolean, nullable = False)
    is_processing = Column(Boolean, nullable = False)

    __table_args__ = (
        PrimaryKeyConstraint(chat_id, author_id, name = "pk_chat_message_burst"),
        ForeignKeyConstraint(
            [chat_id],
            ["chat_configs.chat_id"],
            name = "chat_message_bursts_chat_id_fkey",
            ondelete = "CASCADE",
        ),
        ForeignKeyConstraint(
            [author_id],
            ["simulants.id"],
            name = "chat_message_bursts_author_id_fkey",
            ondelete = "CASCADE",
        ),
    )
