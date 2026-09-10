import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from db.model.chat_message_burst import ChatMessageBurstDB
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.chat.message_burst import ClaimedChatMessageBurst, ScheduledChatMessageBurst
from features.chat.message_burst_repo import ChatMessageBurstRepository
from features.users.user import User


class ChatMessageBurstRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    message_repo: ChatMessageRepository
    repo: ChatMessageBurstRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.message_repo = self.sql.chat_message_repo()
        self.repo = self.sql.chat_message_burst_repo()

    def tearDown(self):
        self.sql.end_session()

    def _create_chat(self, external_id: str) -> ChatConfig:
        return self.sql.chat_config_repo().save(ChatConfig(
            external_id = external_id,
            chat_type = ChatConfigDB.ChatType.telegram,
        ))

    def _create_user(self, external_id: int):
        return self.sql.user_repo().save(User(
            full_name = f"User {external_id}",
            telegram_user_id = external_id,
        ))

    def test_claim_and_finalization_preserve_newer_messages(self):
        chat = self._create_chat("chat1")
        author = self._create_user(1)
        first_message = self.message_repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message1",
            ingestion_order = 1,
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "First",
        ))
        first_scheduled = self.repo.record_message(
            first_message,
            is_addressed = False,
            quiet_period_s = 0,
        )

        first_claim = self.repo.claim(first_scheduled)

        self.assertIsNotNone(first_claim)
        self.assertIsNone(self.repo.claim(first_scheduled))

        second_message = self.message_repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message2",
            ingestion_order = 2,
            author_id = author.id,
            sent_at = first_message.sent_at,
            text = "Second",
        ))
        second_scheduled = self.repo.record_message(
            second_message,
            is_addressed = True,
            quiet_period_s = 0,
        )

        next_scheduled = self.repo.finalize(first_claim)

        self.assertEqual(next_scheduled, second_scheduled)
        second_claim = self.repo.claim(second_scheduled)
        self.assertIsNotNone(second_claim)
        self.assertTrue(second_claim.is_addressed)
        self.assertEqual(second_claim.last_message_ingestion_order, second_message.ingestion_order)

        completed = self.repo.finalize(second_claim)

        self.assertIsNone(completed)
        self.assertEqual(self.sql.get_session().query(ChatMessageBurstDB).count(), 0)

    def test_delete_older_than_uses_strict_cutoff(self):
        chat = self._create_chat("chat1")
        author = self._create_user(1)
        message = self.message_repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "message1",
            ingestion_order = 1,
            author_id = author.id,
            text = "Message",
        ))
        self.repo.record_message(
            message,
            is_addressed = False,
            quiet_period_s = 0,
        )
        process_after = self.sql.get_session().query(ChatMessageBurstDB.process_after).scalar()

        boundary_count = self.repo.delete_older_than(process_after)
        deleted_count = self.repo.delete_older_than(process_after + timedelta(seconds = 1))

        self.assertEqual(boundary_count, 0)
        self.assertEqual(deleted_count, 1)
        self.assertEqual(self.sql.get_session().query(ChatMessageBurstDB).count(), 0)

    def test_finalize_normalizes_timezone_aware_database_time(self):
        database_now = datetime(2026, 1, 2, 12, 0, 0, tzinfo = timezone.utc)
        queued = SimpleNamespace(
            message_count = 2,
            process_after = datetime(2026, 1, 2, 12, 0, 0, 250000),
        )
        db = Mock()
        db.execute.side_effect = [
            Mock(scalar_one = Mock(return_value = database_now)),
            Mock(one_or_none = Mock(return_value = None)),
            Mock(one_or_none = Mock(return_value = queued)),
        ]
        repository = ChatMessageBurstRepository(db)
        claim = ClaimedChatMessageBurst(
            chat_id = UUID(int = 1),
            author_id = UUID(int = 2),
            message_count = 1,
            last_message_sent_at = datetime(2026, 1, 2, 12, 0, 0),
            last_message_ingestion_order = 1,
            is_addressed = False,
        )

        result = repository.finalize(claim)

        self.assertEqual(
            result,
            ScheduledChatMessageBurst(
                chat_id = claim.chat_id,
                author_id = claim.author_id,
                message_count = 2,
                wait_seconds = 0.25,
            ),
        )

    def test_new_message_count_supersedes_old_schedule_before_claim(self):
        chat = self._create_chat("chat1")
        author = self._create_user(1)
        first = self.message_repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "first",
            ingestion_order = 1,
            author_id = author.id,
            text = "First",
        ))
        second = self.message_repo.save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "second",
            ingestion_order = 2,
            author_id = author.id,
            text = "Second",
        ))
        first_scheduled = self.repo.record_message(
            first,
            is_addressed = True,
            quiet_period_s = 0,
        )
        second_scheduled = self.repo.record_message(
            second,
            is_addressed = False,
            quiet_period_s = 0,
        )

        self.assertIsNone(self.repo.claim(first_scheduled))
        claim = self.repo.claim(second_scheduled)
        self.assertIsNotNone(claim)
        self.assertTrue(claim.is_addressed)
