import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_repo import ChatMessageAttachmentRepository
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage


class ChatMessageAttachmentRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatMessageAttachmentRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_message_attachment_repo()

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
        message_id: str,
        attachment_id: str | None = "attach1",
        external_id: str = "external1",
    ) -> ChatMessageAttachment:
        return ChatMessageAttachment(
            id = attachment_id,
            external_id = external_id,
            chat_id = chat_id,
            message_id = message_id,
            size = 1024,
            last_url = "https://example.com/file.jpg",
            last_url_until = 1234567890,
            extension = "jpg",
            mime_type = "image/jpeg",
        )

    def test_save_generates_missing_id(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        attachment = self._attachment(chat.chat_id, "message1", attachment_id = None)

        result = self.repo.save(attachment)

        self.assertIsNotNone(result.id)
        self.assertEqual(len(result.id), 8)
        self.assertEqual(result, replace(attachment, id = result.id))

    def test_save_preserves_deterministic_id(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        attachment = self._attachment(chat.chat_id, "message1", attachment_id = "fixed-id")

        result = self.repo.save(attachment)

        self.assertEqual(result, attachment)

    def test_get_returns_saved_attachment(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        created = self.repo.save(self._attachment(chat.chat_id, "message1"))

        result = self.repo.get("attach1")

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        self.assertIsNone(self.repo.get("missing"))

    def test_get_by_external_id_returns_first_match(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        first = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1"))
        self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach2"))

        result = self.repo.get_by_external_id("external1")

        self.assertEqual(result, first)

    def test_get_by_external_id_returns_none_when_missing(self):
        self.assertIsNone(self.repo.get_by_external_id("missing"))

    def test_get_all_applies_pagination(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1"))
        self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach2"))

        result = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(result), 1)

    def test_get_all_by_message_excludes_other_messages(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        self._create_message(chat.chat_id, "message2")
        first = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach1"))
        second = self.repo.save(self._attachment(chat.chat_id, "message1", attachment_id = "attach2"))
        self.repo.save(self._attachment(chat.chat_id, "message2", attachment_id = "attach3"))

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
            last_url_until = None,
            extension = "png",
            mime_type = "image/png",
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)

    def test_delete_returns_deleted_attachment(self):
        chat = self._create_chat("chat1")
        self._create_message(chat.chat_id, "message1")
        created = self.repo.save(self._attachment(chat.chat_id, "message1"))

        result = self.repo.delete("attach1")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get("attach1"))

    def test_delete_returns_none_when_missing(self):
        self.assertIsNone(self.repo.delete("missing"))

    def test_delete_by_old_messages_uses_strict_cutoff(self):
        chat = self._create_chat("chat1")
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self._create_message(chat.chat_id, "old", sent_at = cutoff - timedelta(seconds = 1))
        self._create_message(chat.chat_id, "boundary", sent_at = cutoff)
        self._create_message(chat.chat_id, "new", sent_at = cutoff + timedelta(seconds = 1))
        self.repo.save(self._attachment(chat.chat_id, "old", attachment_id = "old"))
        self.repo.save(self._attachment(chat.chat_id, "boundary", attachment_id = "boundary"))
        self.repo.save(self._attachment(chat.chat_id, "new", attachment_id = "new"))

        deleted_count = self.repo.delete_by_old_messages(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get("old"))
        self.assertIsNotNone(self.repo.get("boundary"))
        self.assertIsNotNone(self.repo.get("new"))
