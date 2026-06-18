import unittest
from datetime import datetime, timedelta
from uuid import UUID

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from db.schema.chat_message import ChatMessage, ChatMessageSave
from db.schema.chat_message_attachment import ChatMessageAttachment, ChatMessageAttachmentSave
from features.chat.config.chat_config import ChatConfig


class ChatMessageAttachmentCRUDTest(unittest.TestCase):

    sql: SQLUtil

    def setUp(self):
        self.sql = SQLUtil()

    def tearDown(self):
        self.sql.end_session()

    def test_create_attachment(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "attach1",
            external_id = "telegram_file_123",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 1024,
            last_url = "https://example.com/attachment",
            last_url_until = 1234567890,
            extension = "jpg",
            mime_type = "image/jpeg",
        )

        attachment = self.sql.chat_message_attachment_crud().create(attachment_data)

        self.assertEqual(attachment.id, attachment_data.id)
        self.assertEqual(attachment.external_id, attachment_data.external_id)
        self.assertEqual(attachment.chat_id, attachment_data.chat_id)
        self.assertEqual(attachment.message_id, attachment_data.message_id)
        self.assertEqual(attachment.size, attachment_data.size)
        self.assertEqual(attachment.last_url, attachment_data.last_url)
        self.assertEqual(attachment.last_url_until, attachment_data.last_url_until)
        self.assertEqual(attachment.extension, attachment_data.extension)
        self.assertEqual(attachment.mime_type, attachment_data.mime_type)

    def test_create_attachment_auto_generates_id(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            external_id = "telegram_file_auto",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 512,
        )

        attachment = self.sql.chat_message_attachment_crud().create(attachment_data)

        self.assertIsNotNone(attachment.id)
        self.assertEqual(len(str(attachment.id)), 8)  # Short UUID is 8 characters
        self.assertEqual(attachment.external_id, "telegram_file_auto")
        self.assertEqual(attachment.chat_id, chat_message.chat_id)
        self.assertEqual(attachment.message_id, chat_message.message_id)
        self.assertEqual(attachment.size, 512)

    def test_create_with_external_id_only(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            external_id = "telegram_file_only_ext",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
        )

        attachment = self.sql.chat_message_attachment_crud().create(attachment_data)

        self.assertIsNotNone(attachment.id)
        self.assertEqual(attachment.external_id, "telegram_file_only_ext")
        self.assertEqual(attachment.chat_id, chat_message.chat_id)
        self.assertEqual(attachment.message_id, chat_message.message_id)

    def test_get_attachment(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "attach1",
            external_id = "telegram_file_get",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
        )
        created_attachment = self.sql.chat_message_attachment_crud().create(attachment_data)

        fetched_attachment = self.sql.chat_message_attachment_crud().get("attach1")
        assert fetched_attachment is not None

        self.assertEqual(fetched_attachment.id, created_attachment.id)
        self.assertEqual(fetched_attachment.external_id, created_attachment.external_id)
        self.assertEqual(fetched_attachment.chat_id, created_attachment.chat_id)
        self.assertEqual(fetched_attachment.message_id, created_attachment.message_id)

    def test_get_by_external_id(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "attach_ext",
            external_id = "telegram_file_unique_ext",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 2048,
            extension = "png",
        )
        created_attachment = self.sql.chat_message_attachment_crud().create(attachment_data)

        fetched_attachment = self.sql.chat_message_attachment_crud().get_by_external_id("telegram_file_unique_ext")
        assert fetched_attachment is not None

        self.assertEqual(fetched_attachment.id, created_attachment.id)
        self.assertEqual(fetched_attachment.external_id, "telegram_file_unique_ext")
        self.assertEqual(fetched_attachment.chat_id, created_attachment.chat_id)
        self.assertEqual(fetched_attachment.message_id, created_attachment.message_id)
        self.assertEqual(fetched_attachment.size, 2048)
        self.assertEqual(fetched_attachment.extension, "png")

    def test_get_by_external_id_not_found(self):
        fetched_attachment = self.sql.chat_message_attachment_crud().get_by_external_id("non_existent_external_id")
        self.assertIsNone(fetched_attachment)

    def test_get_all_attachments(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachments = [
            self.sql.chat_message_attachment_crud().create(
                ChatMessageAttachmentSave(
                    id = "attach1",
                    external_id = "telegram_file_1",
                    chat_id = chat_message.chat_id,
                    message_id = chat_message.message_id,
                ),
            ),
            self.sql.chat_message_attachment_crud().create(
                ChatMessageAttachmentSave(
                    id = "attach2",
                    external_id = "telegram_file_2",
                    chat_id = chat_message.chat_id,
                    message_id = chat_message.message_id,
                ),
            ),
        ]

        fetched_attachments = self.sql.chat_message_attachment_crud().get_all()

        self.assertEqual(len(fetched_attachments), len(attachments))
        for i in range(len(attachments)):
            self.assertEqual(fetched_attachments[i].id, attachments[i].id)
            self.assertEqual(fetched_attachments[i].external_id, attachments[i].external_id)
            self.assertEqual(fetched_attachments[i].chat_id, attachments[i].chat_id)
            self.assertEqual(fetched_attachments[i].message_id, attachments[i].message_id)

    def test_get_by_message(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachments = [
            self.sql.chat_message_attachment_crud().create(
                ChatMessageAttachmentSave(
                    id = f"attach{i}",
                    external_id = f"telegram_file_{i}",
                    chat_id = chat_message.chat_id,
                    message_id = chat_message.message_id,
                    size = 1024 * i,
                    last_url = f"https://example.com/attachment{i}",
                    last_url_until = 1234567890 + i,
                    extension = "jpg",
                    mime_type = "image/jpeg",
                ),
            )
            for i in range(1, 4)  # Create 3 attachments
        ]

        fetched_attachments = self.sql.chat_message_attachment_crud().get_by_message(
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
        )

        self.assertEqual(len(fetched_attachments), len(attachments))
        for created, fetched in zip(attachments, fetched_attachments):
            self.assertEqual(fetched.id, created.id)
            self.assertEqual(fetched.external_id, created.external_id)
            self.assertEqual(fetched.chat_id, created.chat_id)
            self.assertEqual(fetched.message_id, created.message_id)
            self.assertEqual(fetched.size, created.size)
            self.assertEqual(fetched.last_url, created.last_url)
            self.assertEqual(fetched.last_url_until, created.last_url_until)
            self.assertEqual(fetched.extension, created.extension)
            self.assertEqual(fetched.mime_type, created.mime_type)

        non_existent_attachments = self.sql.chat_message_attachment_crud().get_by_message(
            chat_id = UUID(int = 999),
            message_id = "non_existent_message",
        )
        self.assertEqual(len(non_existent_attachments), 0)

    def test_update_attachment(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, World!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "att1",
            external_id = "telegram_file_update",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
        )
        created_attachment_db = self.sql.chat_message_attachment_crud().create(attachment_data)
        created_attachment = ChatMessageAttachment.model_validate(created_attachment_db)

        update_data = ChatMessageAttachmentSave(
            id = created_attachment.id,
            external_id = "telegram_file_updated",
            chat_id = created_attachment.chat_id,
            message_id = created_attachment.message_id,
            size = 2048,
            last_url = "https://example.com/newfile",
            last_url_until = 9876543210,
            extension = "png",
            mime_type = "image/png",
        )
        updated_attachment_db = self.sql.chat_message_attachment_crud().update(update_data)
        updated_attachment = ChatMessageAttachment.model_validate(updated_attachment_db)

        self.assertEqual(updated_attachment.id, created_attachment.id)
        self.assertEqual(updated_attachment.external_id, "telegram_file_updated")
        self.assertEqual(updated_attachment.chat_id, created_attachment.chat_id)
        self.assertEqual(updated_attachment.message_id, created_attachment.message_id)
        self.assertEqual(updated_attachment.size, update_data.size)
        self.assertEqual(updated_attachment.last_url, update_data.last_url)
        self.assertEqual(updated_attachment.last_url_until, update_data.last_url_until)
        self.assertEqual(updated_attachment.extension, update_data.extension)
        self.assertEqual(updated_attachment.mime_type, update_data.mime_type)

    def test_save_attachment(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "attach1",
            external_id = "telegram_file_save",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 1024,
            last_url = "https://example.com/attachment",
            last_url_until = 1234567890,
            extension = "jpg",
            mime_type = "image/jpeg",
        )

        # First, save should create the record
        saved_attachment = self.sql.chat_message_attachment_crud().save(attachment_data)
        self.assertIsNotNone(saved_attachment)
        self.assertEqual(saved_attachment.id, attachment_data.id)
        self.assertEqual(saved_attachment.external_id, attachment_data.external_id)
        self.assertEqual(saved_attachment.chat_id, attachment_data.chat_id)
        self.assertEqual(saved_attachment.message_id, attachment_data.message_id)
        self.assertEqual(saved_attachment.size, attachment_data.size)
        self.assertEqual(saved_attachment.last_url, attachment_data.last_url)
        self.assertEqual(saved_attachment.last_url_until, attachment_data.last_url_until)
        self.assertEqual(saved_attachment.extension, attachment_data.extension)
        self.assertEqual(saved_attachment.mime_type, attachment_data.mime_type)

        # Now, save should update the existing record
        update_data = ChatMessageAttachmentSave(
            id = attachment_data.id,
            external_id = "telegram_file_save_updated",
            chat_id = attachment_data.chat_id,
            message_id = attachment_data.message_id,
            last_url = "https://example.com/newfile",
        )
        updated_attachment = self.sql.chat_message_attachment_crud().save(update_data)
        self.assertIsNotNone(updated_attachment)
        self.assertEqual(updated_attachment.id, attachment_data.id)
        self.assertEqual(updated_attachment.external_id, "telegram_file_save_updated")
        self.assertEqual(updated_attachment.chat_id, attachment_data.chat_id)
        self.assertEqual(updated_attachment.message_id, attachment_data.message_id)
        self.assertEqual(updated_attachment.size, update_data.size)
        self.assertEqual(updated_attachment.last_url, update_data.last_url)
        self.assertEqual(updated_attachment.last_url_until, update_data.last_url_until)
        self.assertEqual(updated_attachment.extension, update_data.extension)
        self.assertEqual(updated_attachment.mime_type, update_data.mime_type)

    def test_save_attachment_auto_generates_id(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            external_id = "telegram_file_save_auto",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 4096,
        )

        # Save should create the record with auto-generated ID
        saved_attachment_db = self.sql.chat_message_attachment_crud().save(attachment_data)
        saved_attachment = ChatMessageAttachment.model_validate(saved_attachment_db)

        self.assertIsNotNone(saved_attachment.id)
        self.assertEqual(len(saved_attachment.id), 8)  # Short UUID
        self.assertEqual(saved_attachment.external_id, "telegram_file_save_auto")
        self.assertEqual(saved_attachment.size, 4096)

    def test_delete_attachment(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, World!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        attachment_data = ChatMessageAttachmentSave(
            id = "att1",
            external_id = "telegram_file_delete",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
        )
        created_attachment_db = self.sql.chat_message_attachment_crud().create(attachment_data)
        created_attachment = ChatMessageAttachment.model_validate(created_attachment_db)

        deleted_attachment_db = self.sql.chat_message_attachment_crud().delete(created_attachment.id)
        deleted_attachment = ChatMessageAttachment.model_validate(deleted_attachment_db)

        self.assertEqual(deleted_attachment.id, created_attachment.id)
        self.assertEqual(deleted_attachment.external_id, created_attachment.external_id)
        self.assertEqual(deleted_attachment.chat_id, created_attachment.chat_id)
        self.assertEqual(deleted_attachment.message_id, created_attachment.message_id)
        self.assertIsNone(self.sql.chat_message_attachment_crud().get(created_attachment.id))

    def test_integration_id_and_external_id_relationship(self):
        """Test the relationship between id and external_id fields"""
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        chat_message_db = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "msg1",
                text = "Hello, world!",
            ),
        )
        chat_message = ChatMessage.model_validate(chat_message_db)
        # Create attachment with both id and external_id
        attachment_data = ChatMessageAttachmentSave(
            id = "custom_id_123",
            external_id = "telegram_external_456",
            chat_id = chat_message.chat_id,
            message_id = chat_message.message_id,
            size = 1024,
        )
        created_attachment_db = self.sql.chat_message_attachment_crud().create(attachment_data)
        ChatMessageAttachment.model_validate(created_attachment_db)

        # Should be able to find by both IDs
        by_id_db = self.sql.chat_message_attachment_crud().get("custom_id_123")
        by_id = ChatMessageAttachment.model_validate(by_id_db)

        by_external_id_db = self.sql.chat_message_attachment_crud().get_by_external_id("telegram_external_456")
        by_external_id = ChatMessageAttachment.model_validate(by_external_id_db)

        self.assertIsNotNone(by_id)
        self.assertIsNotNone(by_external_id)
        self.assertEqual(by_id.id, by_external_id.id)
        self.assertEqual(by_id.external_id, by_external_id.external_id)
        self.assertEqual(by_id.size, by_external_id.size)

        # Both lookups should return the same record
        self.assertEqual(by_id.id, "custom_id_123")
        self.assertEqual(by_id.external_id, "telegram_external_456")

    def test_delete_by_old_messages(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        old_message = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "old_msg",
                sent_at = datetime.now() - timedelta(days = 31),
                text = "Old",
            ),
        )
        recent_message = self.sql.chat_message_crud().create(
            ChatMessageSave(
                chat_id = chat.chat_id,
                message_id = "recent_msg",
                sent_at = datetime.now(),
                text = "Recent",
            ),
        )
        old_attachment = self.sql.chat_message_attachment_crud().create(
            ChatMessageAttachmentSave(
                id = "attach_old",
                chat_id = old_message.chat_id,
                message_id = old_message.message_id,
            ),
        )
        recent_attachment = self.sql.chat_message_attachment_crud().create(
            ChatMessageAttachmentSave(
                id = "attach_recent",
                chat_id = recent_message.chat_id,
                message_id = recent_message.message_id,
            ),
        )
        old_attachment_id, recent_attachment_id = old_attachment.id, recent_attachment.id
        cutoff = datetime.now() - timedelta(days = 30)

        deleted_count = self.sql.chat_message_attachment_crud().delete_by_old_messages(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.sql.chat_message_attachment_crud().get(old_attachment_id))
        self.assertIsNotNone(self.sql.chat_message_attachment_crud().get(recent_attachment_id))
