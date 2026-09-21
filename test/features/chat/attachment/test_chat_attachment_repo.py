import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import count
from uuid import uuid4

import stubs
from db.sql_util import SQLUtil

from features.chat.attachment.chat_attachment_repo import ChatAttachmentRepository


class ChatAttachmentRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatAttachmentRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_attachment_repo()
        self.message_order = count(1)

    def tearDown(self):
        self.sql.end_session()

    def test_save_preserves_generated_id(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        uploader = self.sql.user_repo().save(stubs.domain.user(full_name = "Uploader"))
        attachment = stubs.domain.chat_attachment(
            id = uuid4().hex[:8],
            chat_id = chat.chat_id,
            uploader_user_id = uploader.id,
            message_id = "message1",
        )

        result = self.repo.save(attachment)

        self.assertEqual(len(result.id), 8)
        self.assertEqual(result, attachment)

    def test_save_preserves_deterministic_id(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        attachment = stubs.domain.chat_attachment(
            chat_id = chat.chat_id,
            message_id = "message1",
            id = "fixed-id",
        )

        result = self.repo.save(attachment)

        self.assertEqual(result, attachment)

    def test_save_allows_chat_owned_attachment_without_message_id(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        attachment = stubs.domain.chat_attachment(
            chat_id = chat.chat_id,
            message_id = None,
        )

        result = self.repo.save(attachment)

        self.assertEqual(result, attachment)
        self.assertIsNone(result.message_id)

    def test_get_returns_saved_attachment(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
            ),
        )

        result = self.repo.get(created.id)

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        self.assertIsNone(self.repo.get("missing"))

    def test_get_by_external_id_returns_chat_match(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        first = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
                id = "attachment-2",
                external_id = "telegram-file-2",
            ),
        )

        result = self.repo.get_by_external_id(chat.chat_id, first.external_id)

        self.assertEqual(result, first)

    def test_get_by_external_id_returns_none_when_missing(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )

        self.assertIsNone(self.repo.get_by_external_id(chat.chat_id, "missing"))

    def test_get_by_external_id_returns_none_for_other_chat(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat2",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = first_chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        first = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = first_chat.chat_id,
                message_id = "message1",
            ),
        )

        self.assertIsNone(self.repo.get_by_external_id(second_chat.chat_id, first.external_id))

    def test_get_all_applies_pagination(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
                id = "attachment-2",
                external_id = "telegram-file-2",
            ),
        )

        result = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(result), 1)

    def test_get_all_by_message_excludes_other_messages(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message2",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message2",
            ),
        )
        first = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
            ),
        )
        second = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
                id = "attachment-2",
                external_id = "telegram-file-2",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message2",
                id = "attachment-3",
                external_id = "telegram-file-3",
            ),
        )

        result = self.repo.get_all_by_message(chat.chat_id, "message1")

        self.assertEqual({attachment.id for attachment in result}, {first.id, second.id})

    def test_save_replaces_every_non_id_field(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat2",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = first_chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = second_chat.chat_id,
                message_id = "message2",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message2",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = first_chat.chat_id,
                message_id = "message1",
            ),
        )
        replacement = replace(
            created,
            external_id = "external2",
            chat_id = second_chat.chat_id,
            message_id = "message2",
            size = None,
            last_url = None,
            extension = "png",
            mime_type = "image/png",
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)

    def test_save_replaces_by_remote_identity_when_id_differs(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
                id = "old-id",
            ),
        )
        replacement = replace(
            created,
            id = "new-id",
            size = 2048,
            last_url = "https://example.com/new.jpg",
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replace(replacement, id = created.id))
        self.assertEqual(self.repo.get("old-id"), result)
        self.assertIsNone(self.repo.get("new-id"))

    def test_save_does_not_replace_remote_identity_from_another_chat(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat2",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = first_chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = second_chat.chat_id,
                message_id = "message2",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message2",
            ),
        )
        first = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = first_chat.chat_id,
                message_id = "message1",
            ),
        )
        second = stubs.domain.chat_attachment(
            chat_id = second_chat.chat_id,
            message_id = "message2",
            id = "second-id",
            external_id = first.external_id,
        )

        result = self.repo.save(second)

        self.assertEqual(result, second)
        self.assertEqual(self.repo.get(first.id), first)
        self.assertEqual(self.repo.get(second.id), second)

    def test_delete_returns_deleted_attachment(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "message1",
                ingestion_order = next(self.message_order),
                sent_at = datetime.now(),
                text = "message1",
            ),
        )
        created = self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "message1",
            ),
        )

        result = self.repo.delete(created.id)

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(created.id))

    def test_delete_returns_none_when_missing(self):
        self.assertIsNone(self.repo.delete("missing"))

    def test_delete_stale_by_old_messages(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "old",
                ingestion_order = next(self.message_order),
                sent_at = cutoff - timedelta(seconds = 1) or datetime.now(),
                text = "old",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "boundary",
                ingestion_order = next(self.message_order),
                sent_at = cutoff or datetime.now(),
                text = "boundary",
            ),
        )
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "new",
                ingestion_order = next(self.message_order),
                sent_at = cutoff + timedelta(seconds = 1) or datetime.now(),
                text = "new",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "old",
                id = "old",
                external_id = "telegram-file-old",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "boundary",
                id = "boundary",
                external_id = "telegram-file-boundary",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "new",
                id = "new",
                external_id = "telegram-file-new",
            ),
        )

        deleted = self.repo.delete_stale(cutoff)

        self.assertEqual([a.id for a in deleted], ["old"])
        self.assertIsNone(self.repo.get("old"))
        self.assertIsNotNone(self.repo.get("boundary"))
        self.assertIsNotNone(self.repo.get("new"))

    def test_delete_stale_only_orphans(self):
        chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(
                chat_id = None,
                external_id = "chat1",
            ),
        )
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        # old unlinked orphan
        old_attachment = stubs.domain.chat_attachment(
            chat_id = chat.chat_id,
            message_id = None,
            id = "orphan1",
            external_id = "telegram-file-orphan-1",
        )
        old_attachment = replace(old_attachment, created_at = cutoff - timedelta(days = 1))
        self.repo.save(old_attachment)
        # fresh unlinked (should survive)
        new_attachment = stubs.domain.chat_attachment(
            chat_id = chat.chat_id,
            message_id = None,
            id = "kept1",
            external_id = "telegram-file-kept-1",
        )
        new_attachment = replace(new_attachment, created_at = cutoff + timedelta(days = 1))
        self.repo.save(new_attachment)
        # message-linked attachment (should survive)
        self.sql.chat_message_repo().save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "msg1",
                ingestion_order = next(self.message_order),
                sent_at = cutoff - timedelta(days = 1) or datetime.now(),
                text = "msg1",
            ),
        )
        self.repo.save(
            stubs.domain.chat_attachment(
                chat_id = chat.chat_id,
                message_id = "msg1",
                id = "kept2",
                external_id = "telegram-file-kept-2",
            ),
        )

        deleted = self.repo.delete_stale(cutoff, only_orphans = True)

        self.assertEqual([a.id for a in deleted], ["orphan1"])
        self.assertIsNone(self.repo.get("orphan1"))
        self.assertIsNotNone(self.repo.get("kept1"))
        self.assertIsNotNone(self.repo.get("kept2"))
