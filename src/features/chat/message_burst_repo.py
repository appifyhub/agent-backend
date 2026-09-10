from datetime import datetime, timedelta

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.model.chat_message_burst import ChatMessageBurstDB
from features.chat.message.chat_message import ChatMessage
from features.chat.message_burst import ClaimedChatMessageBurst, ScheduledChatMessageBurst
from util.error_codes import UNEXPECTED_ERROR
from util.errors import InternalError


class ChatMessageBurstRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def record_message(
        self,
        message: ChatMessage,
        is_addressed: bool,
        quiet_period_s: float,
    ) -> ScheduledChatMessageBurst:
        if message.author_id is None or message.ingestion_order is None:
            raise InternalError("Stored burst messages require an author and ingestion order", UNEXPECTED_ERROR)

        database_now = self._db.execute(select(func.now())).scalar_one()
        process_after = database_now + timedelta(seconds = quiet_period_s)
        insert_statement = insert(ChatMessageBurstDB).values(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 1,
            process_after = process_after,
            last_message_sent_at = message.sent_at,
            last_message_ingestion_order = message.ingestion_order,
            is_addressed = is_addressed,
            is_processing = False,
        )
        excluded = insert_statement.excluded
        last_message_is_newer = or_(
            excluded.last_message_sent_at > ChatMessageBurstDB.last_message_sent_at,
            and_(
                excluded.last_message_sent_at == ChatMessageBurstDB.last_message_sent_at,
                excluded.last_message_ingestion_order > ChatMessageBurstDB.last_message_ingestion_order,
            ),
        )
        statement = insert_statement.on_conflict_do_update(
            index_elements = [ChatMessageBurstDB.chat_id, ChatMessageBurstDB.author_id],
            set_ = {
                "message_count": ChatMessageBurstDB.message_count + 1,
                "process_after": excluded.process_after,
                "last_message_sent_at": case(
                    (last_message_is_newer, excluded.last_message_sent_at),
                    else_ = ChatMessageBurstDB.last_message_sent_at,
                ),
                "last_message_ingestion_order": case(
                    (last_message_is_newer, excluded.last_message_ingestion_order),
                    else_ = ChatMessageBurstDB.last_message_ingestion_order,
                ),
                "is_addressed": or_(
                    ChatMessageBurstDB.is_addressed,
                    excluded.is_addressed,
                ),
            },
        ).returning(
            ChatMessageBurstDB.chat_id,
            ChatMessageBurstDB.author_id,
            ChatMessageBurstDB.message_count,
        )
        row = self._db.execute(statement).one()
        self._db.commit()
        return ScheduledChatMessageBurst(
            chat_id = row.chat_id,
            author_id = row.author_id,
            message_count = row.message_count,
            wait_seconds = quiet_period_s,
        )

    def claim(
        self,
        scheduled: ScheduledChatMessageBurst,
    ) -> ClaimedChatMessageBurst | None:
        database_now = self._db.execute(select(func.now())).scalar_one()
        statement = update(ChatMessageBurstDB).where(
            ChatMessageBurstDB.chat_id == scheduled.chat_id,
            ChatMessageBurstDB.author_id == scheduled.author_id,
            ChatMessageBurstDB.message_count == scheduled.message_count,
            ChatMessageBurstDB.process_after <= database_now,
            ChatMessageBurstDB.is_processing.is_(False),
        ).values(
            is_processing = True,
        ).returning(
            ChatMessageBurstDB.message_count,
            ChatMessageBurstDB.last_message_sent_at,
            ChatMessageBurstDB.last_message_ingestion_order,
            ChatMessageBurstDB.is_addressed,
        )
        row = self._db.execute(statement).one_or_none()
        self._db.commit()
        if row is None:
            return None
        return ClaimedChatMessageBurst(
            chat_id = scheduled.chat_id,
            author_id = scheduled.author_id,
            message_count = row.message_count,
            last_message_sent_at = row.last_message_sent_at,
            last_message_ingestion_order = row.last_message_ingestion_order,
            is_addressed = row.is_addressed,
        )

    def finalize(
        self,
        claimed: ClaimedChatMessageBurst,
    ) -> ScheduledChatMessageBurst | None:
        database_now = self._db.execute(select(func.now())).scalar_one()
        completed = self._db.execute(
            delete(ChatMessageBurstDB).where(
                ChatMessageBurstDB.chat_id == claimed.chat_id,
                ChatMessageBurstDB.author_id == claimed.author_id,
                ChatMessageBurstDB.message_count == claimed.message_count,
                ChatMessageBurstDB.is_processing.is_(True),
            ).returning(ChatMessageBurstDB.message_count),
        ).one_or_none()

        if completed is not None:
            self._db.commit()
            return None

        queued = self._db.execute(
            update(ChatMessageBurstDB).where(
                ChatMessageBurstDB.chat_id == claimed.chat_id,
                ChatMessageBurstDB.author_id == claimed.author_id,
                ChatMessageBurstDB.is_processing.is_(True),
            ).values(
                is_processing = False,
            ).returning(
                ChatMessageBurstDB.message_count,
                ChatMessageBurstDB.process_after,
            ),
        ).one_or_none()

        self._db.commit()
        if queued is None:
            return None

        return ScheduledChatMessageBurst(
            chat_id = claimed.chat_id,
            author_id = claimed.author_id,
            message_count = queued.message_count,
            wait_seconds = max(
                0.0,
                (queued.process_after - database_now).total_seconds(),
            ),
        )

    def delete_older_than(self, cutoff: datetime) -> int:
        deleted_count = self._db.query(ChatMessageBurstDB).filter(
            ChatMessageBurstDB.process_after < cutoff,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count
