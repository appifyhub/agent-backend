import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import count
from uuid import NAMESPACE_URL, uuid5

import stubs
from db.sql_util import SQLUtil
from sqlalchemy import Connection, event

from db.model.chat_message import ChatMessageDB
from features.chat.message.chat_message_repo import ChatMessageRepository

_ingestion_order = count(1)


def _assign_sqlite_ingestion_order(
    _mapper,
    connection: Connection,
    target: ChatMessageDB,
) -> None:
    if connection.dialect.name != "sqlite" or target.ingestion_order is not None:
        return
    target.ingestion_order = next(_ingestion_order)


def setUpModule() -> None:
    event.listen(ChatMessageDB, "before_insert", _assign_sqlite_ingestion_order)


def tearDownModule() -> None:
    event.remove(ChatMessageDB, "before_insert", _assign_sqlite_ingestion_order)


class ChatMessageRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatMessageRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_message_repo()

    def tearDown(self):
        self.sql.end_session()

    def test_save_inserts_complete_message(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        author = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid5(NAMESPACE_URL, "user:1"),
                telegram_user_id = 1,
                whatsapp_user_id = None,
                connect_key = "TEST-USER-1",
            ),
        )
        message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message1",
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "Hello",
            ingestion_order = None,
        )

        result = self.repo.save(message)

        self.assertEqual(result, replace(message, ingestion_order = result.ingestion_order))
        self.assertIsNotNone(result.ingestion_order)

    def test_get_uses_composite_identity(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat2"),
                external_id = "chat2",
            ),
        )
        first = self.repo.save(
            stubs.domain.chat_message(
                chat_id = first_chat.chat_id,
                message_id = "same",
                text = "First",
                author_id = None,
                ingestion_order = None,
            ),
        )
        second = self.repo.save(
            stubs.domain.chat_message(
                chat_id = second_chat.chat_id,
                message_id = "same",
                text = "Second",
                author_id = None,
                ingestion_order = None,
            ),
        )

        self.assertEqual(self.repo.get(first_chat.chat_id, "same"), first)
        self.assertEqual(self.repo.get(second_chat.chat_id, "same"), second)

    def test_get_returns_none_when_missing(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )

        self.assertIsNone(self.repo.get(chat.chat_id, "missing"))

    def test_get_all_applies_pagination(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                text = "First",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message2",
                text = "Second",
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_all(skip = 1, limit = 1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].message_id, "message2")

    def test_get_latest_by_chat_orders_and_paginates(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat2"),
                external_id = "chat2",
            ),
        )
        base_time = datetime(2026, 1, 2, 12, 0, 0)
        for i in range(4):
            self.repo.save(
                stubs.domain.chat_message(
                    chat_id = first_chat.chat_id,
                    message_id = f"message{i}",
                    sent_at = base_time + timedelta(minutes = i),
                    text = str(i),
                    author_id = None,
                    ingestion_order = None,
                ),
            )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = second_chat.chat_id,
                message_id = "other",
                sent_at = base_time + timedelta(hours = 1),
                text = "Other",
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_latest_by_chat(first_chat.chat_id, skip = 1, limit = 2)

        self.assertEqual([message.message_id for message in result], ["message2", "message1"])

    def test_get_latest_by_chat_excludes_temporary_messages_by_default(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        base_time = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                sent_at = base_time,
                text = "Visible",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "outgoing-abc123",
                sent_at = base_time + timedelta(minutes = 1),
                text = "Temporary",
                is_temporary = True,
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_latest_by_chat(chat.chat_id)

        self.assertEqual([message.message_id for message in result], ["message1"])

    def test_get_latest_by_chat_can_include_temporary_messages(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        base_time = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                sent_at = base_time,
                text = "Visible",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "outgoing-abc123",
                sent_at = base_time + timedelta(minutes = 1),
                text = "Temporary",
                is_temporary = True,
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_latest_by_chat(chat.chat_id, include_temporary = True)

        self.assertEqual(
            [message.message_id for message in result],
            ["outgoing-abc123", "message1"],
        )

    def test_get_latest_by_chat_keeps_prefixed_non_temporary_messages(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "outgoing-abc123",
                text = "Permanent",
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_latest_by_chat(chat.chat_id)

        self.assertEqual([message.message_id for message in result], ["outgoing-abc123"])

    def test_get_latest_by_chat_filters_temporary_messages_before_pagination(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        base_time = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                sent_at = base_time,
                text = "Visible 1",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message2",
                sent_at = base_time + timedelta(minutes = 1),
                text = "Visible 2",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "outgoing-abc123",
                sent_at = base_time + timedelta(minutes = 2),
                text = "Temporary",
                is_temporary = True,
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.get_latest_by_chat(chat.chat_id, limit = 2)

        self.assertEqual([message.message_id for message in result], ["message2", "message1"])

    def test_save_exactly_replaces_non_identity_fields_from_independent_snapshot(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        first_author = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid5(NAMESPACE_URL, "user:1"),
                telegram_user_id = 1,
                whatsapp_user_id = None,
                connect_key = "TEST-USER-1",
            ),
        )
        second_author = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid5(NAMESPACE_URL, "user:2"),
                telegram_user_id = 2,
                whatsapp_user_id = None,
                connect_key = "TEST-USER-2",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                author_id = first_author.id,
                sent_at = datetime(2026, 1, 2, 12, 0, 0),
                text = "Original",
                ingestion_order = None,
            ),
        )
        original_snapshot = replace(created)
        replacement = replace(
            created,
            author_id = second_author.id,
            sent_at = datetime(2026, 1, 2, 13, 0, 0),
            text = "Replacement",
            is_temporary = True,
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)
        self.assertEqual(created, original_snapshot)
        self.assertNotEqual(result.author_id, original_snapshot.author_id)
        self.assertNotEqual(result.sent_at, original_snapshot.sent_at)
        self.assertNotEqual(result.text, original_snapshot.text)
        self.assertNotEqual(result.is_temporary, original_snapshot.is_temporary)

    def test_save_can_clear_optional_author(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        author = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid5(NAMESPACE_URL, "user:1"),
                telegram_user_id = 1,
                whatsapp_user_id = None,
                connect_key = "TEST-USER-1",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                author_id = author.id,
                text = "Hello",
                ingestion_order = None,
            ),
        )

        result = self.repo.save(replace(created, author_id = None))

        self.assertIsNone(result.author_id)

    def test_delete_returns_deleted_message(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                text = "Hello",
                author_id = None,
                ingestion_order = None,
            ),
        )

        result = self.repo.delete(chat.chat_id, "message1")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(chat.chat_id, "message1"))

    def test_delete_returns_none_when_missing(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )

        self.assertIsNone(self.repo.delete(chat.chat_id, "missing"))

    def test_delete_older_than_uses_strict_cutoff(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "old",
                sent_at = cutoff - timedelta(seconds = 1),
                text = "Old",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "boundary",
                sent_at = cutoff,
                text = "Boundary",
                author_id = None,
                ingestion_order = None,
            ),
        )
        self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "new",
                sent_at = cutoff + timedelta(seconds = 1),
                text = "New",
                author_id = None,
                ingestion_order = None,
            ),
        )

        deleted_count = self.repo.delete_older_than(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(chat.chat_id, "old"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, "boundary"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, "new"))

    def test_equal_timestamps_use_ingestion_order_for_history_cutoff(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = uuid5(NAMESPACE_URL, "chat:chat1"),
                external_id = "chat1",
            ),
        )
        sent_at = datetime(2026, 1, 2, 12, 0, 0)
        first = self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "first",
                sent_at = sent_at,
                text = "First",
                author_id = None,
                ingestion_order = None,
            ),
        )
        second = self.repo.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "second",
                sent_at = sent_at,
                text = "Second",
                author_id = None,
                ingestion_order = None,
            ),
        )

        latest = self.repo.get_latest_by_chat(chat.chat_id)
        through_first = self.repo.get_latest_by_chat(
            chat.chat_id,
            cutoff_sent_at = first.sent_at,
            cutoff_ingestion_order = first.ingestion_order,
        )

        self.assertEqual([message.message_id for message in latest], ["second", "first"])
        self.assertEqual([message.message_id for message in through_first], ["first"])
        self.assertGreater(second.ingestion_order, first.ingestion_order)
