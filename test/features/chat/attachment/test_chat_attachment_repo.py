import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_repo import ChatAttachmentRepository
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.users.user import User


class ChatAttachmentRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatAttachmentRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_attachment_repo()
        self.uploader = self.sql.user_repo().save(User(full_name = "Uploader"))

    def tearDown(self):
        self.sql.end_session()

    def _create_chat(self, external_id: str) -> ChatConfig:
        return self.sql.chat_config_repo().save(ChatConfig(
            external_id = external_id,
            chat_type = ChatConfigDB.ChatType.telegram,
        ))

    def _create_message(
        self,
        chat_id: UUID,
        message_id: str,
        sent_at: datetime | None = None,
    ) -> None:
        self.sql.chat_message_repo().save(ChatMessage(
            chat_id = chat_id,
            message_id = message_id,
            sent_at = sent_at or datetime.now(),
            text = message_id,
        ))

    def _attachment(
        self,
        chat_id: UUID,
        message_id: str | None,
        attachment_id: str = "attach1",
        external_id: str = "external1",
    ) -> ChatAttachment:
        return ChatAttachment(
            id = attachment_id,
            external_id = external_id,
            chat_id = chat_id,
            uploader_user_id = self.uploader.id,
            message_id = message_id,
            size = 1024,
            last_url = "https://example.com/file.jpg",
            extension = "jpg",
            mime_type = "image/jpeg",
        )

    def test_new_attachment_generates_id_before_save(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        attachment = ChatAttachment(
            external_id = "external1",
            chat_id = chat.chat_id,
            uploader_user_id = self.uploader.id,
            message_id = "message1",
            size = 1024,
            last_url = "https://example.com/file.jpg",
            extension = "jpg",
            mime_type = "image/jpeg",
        )

        result = self.repo.save(attachment)

        self.assertEqual(len(result.id), 8)
        self.assertEqual(result, attachment)

    def test_save_preserves_deterministic_id(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        attachment = self._attachment(chat.chat_id, "message1", attachment_id = "fixed-id")

        result = self.repo.save(attachment)

        self.assertEqual(result, attachment)

    def test_save_allows_chat_owned_attachment_without_message_id(self):
        chat = self._create_chat("chat1")
        attachment = self._attachment(chat.chat_id, None, attachment_id = "chat-attachment")

        result = self.repo.save(attachment)

        self.assertEqual(result, attachment)
        self.assertIsNone(result.message_id)

    def test_get_returns_saved_attachment(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        created = self.repo.save(self._attachment(chat.chat_id, "message1"))

        result = self.repo.get("attach1")

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        self.assertIsNone(self.repo.get("missing"))

    def test_get_by_external_id_returns_chat_match(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        first = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1"))
        self.repo.save(self._attachment(
            chat.chat_id,
            "message1",
            attachment_id = "attach2",
            external_id = "external2",
        ))

        result = self.repo.get_by_external_id(chat.chat_id, "external1")

        self.assertEqual(result, first)

    def test_get_by_external_id_returns_none_when_missing(self):
        chat = self._create_chat("chat1")

        self.assertIsNone(self.repo.get_by_external_id(chat.chat_id, "missing"))

    def test_get_by_external_id_returns_none_for_other_chat(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        self._create_message(first_chat.chat_id, "message1")
        self.repo.save(self._attachment(first_chat.chat_id, "message1", attachment_id = "attach1"))

        self.assertIsNone(self.repo.get_by_external_id(second_chat.chat_id, "external1"))

    def test_get_all_applies_pagination(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1", external_id = "external1"))
        self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach2", external_id = "external2"))

        result = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(result), 1)

    def test_get_all_by_message_excludes_other_messages(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        self._create_message(chat.chat_id, "message2")
        first = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1", external_id = "external1"))
        second = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach2", external_id = "external2"))
        self.repo.save(self._attachment(chat.chat_id, "message2", attachment_id = "attach3", external_id = "external3"))

        result = self.repo.get_all_by_message(chat.chat_id, "message1")

        self.assertEqual({attachment.id for attachment in result}, {first.id, second.id})

    def test_save_replaces_every_non_id_field(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        self._create_message(first_chat.chat_id, "message1")
        self._create_message(second_chat.chat_id, "message2")
        created = self.repo.save(self._attachment(first_chat.chat_id, "message1"))
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
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        created = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "old-id"))
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
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        self._create_message(first_chat.chat_id, "message1")
        self._create_message(second_chat.chat_id, "message2")
        first = self.repo.save(self._attachment(first_chat.chat_id, "message1", attachment_id = "first-id"))
        second = self._attachment(
            second_chat.chat_id,
            "message2",
            attachment_id = "second-id",
            external_id = first.external_id,
        )

        result = self.repo.save(second)

        self.assertEqual(result, second)
        self.assertEqual(self.repo.get("first-id"), first)
        self.assertEqual(self.repo.get("second-id"), second)

    def test_delete_returns_deleted_attachment(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        created = self.repo.save(self._attachment(chat.chat_id, "message1"))

        result = self.repo.delete("attach1")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get("attach1"))

    def test_delete_returns_none_when_missing(self):
        self.assertIsNone(self.repo.delete("missing"))

    def test_delete_stale_by_old_messages(self):
        chat = self._create_chat("chat1")
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self._create_message(chat.chat_id, "old", sent_at = cutoff - timedelta(seconds = 1))
        self._create_message(chat.chat_id, "boundary", sent_at = cutoff)
        self._create_message(chat.chat_id, "new", sent_at = cutoff + timedelta(seconds = 1))
        self.repo.save(self._attachment(chat.chat_id, "old", attachment_id = "old", external_id = "external-old"))
        self.repo.save(self._attachment(chat.chat_id, "boundary", attachment_id = "boundary", external_id = "external-boundary"))
        self.repo.save(self._attachment(chat.chat_id, "new", attachment_id = "new", external_id = "external-new"))

        deleted = self.repo.delete_stale(cutoff)

        self.assertEqual([a.id for a in deleted], ["old"])
        self.assertIsNone(self.repo.get("old"))
        self.assertIsNotNone(self.repo.get("boundary"))
        self.assertIsNotNone(self.repo.get("new"))

    def test_delete_stale_only_orphans(self):
        chat = self._create_chat("chat1")
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        # old unlinked orphan
        old_attachment = self._attachment(chat.chat_id, None, attachment_id = "orphan1", external_id = "ext1")
        old_attachment = replace(old_attachment, created_at = cutoff - timedelta(days = 1))
        self.repo.save(old_attachment)
        # fresh unlinked (should survive)
        new_attachment = self._attachment(chat.chat_id, None, attachment_id = "kept1", external_id = "ext2")
        new_attachment = replace(new_attachment, created_at = cutoff + timedelta(days = 1))
        self.repo.save(new_attachment)
        # message-linked attachment (should survive)
        self._create_message(chat.chat_id, "msg1", sent_at = cutoff - timedelta(days = 1))
        self.repo.save(self._attachment(chat.chat_id, "msg1", attachment_id = "kept2", external_id = "ext3"))

        deleted = self.repo.delete_stale(cutoff, only_orphans = True)

        self.assertEqual([a.id for a in deleted], ["orphan1"])
        self.assertIsNone(self.repo.get("orphan1"))
        self.assertIsNotNone(self.repo.get("kept1"))
        self.assertIsNotNone(self.repo.get("kept2"))
