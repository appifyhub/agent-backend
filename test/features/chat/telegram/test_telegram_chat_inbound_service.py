import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.telegram.model.attachment.document import Document
from features.chat.telegram.model.attachment.video import Video
from features.chat.telegram.model.chat import Chat
from features.chat.telegram.model.message import Message
from features.chat.telegram.model.text_quote import TextQuote
from features.chat.telegram.model.update import Update
from features.chat.telegram.model.user import User as TelegramUser
from features.chat.telegram.telegram_chat_inbound_service import TelegramChatInboundService
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.integrations.integrations import resolve_agent_user
from features.users.user import User
from features.users.user_remote_data import UserRemoteData
from util.config import config
from util.errors import InternalError
from util.functions import generate_deterministic_short_uuid


class TelegramChatInboundServiceTest(unittest.TestCase):

    sql: SQLUtil
    mock_di: DI
    resolver: TelegramChatInboundService

    def setUp(self):
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        self.sql = SQLUtil()
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.chat_config_repo = self.sql.chat_config_repo()
        # noinspection PyPropertyAccess
        self.mock_di.user_repo = self.sql.user_repo()
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_repo = self.sql.chat_message_repo()
        # noinspection PyPropertyAccess
        self.mock_di.chat_attachment_repo = self.sql.chat_attachment_repo()
        # noinspection PyPropertyAccess
        self.mock_di.chat_attachment_service = ChatAttachmentService(self.mock_di)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_api = MagicMock()
        self.mock_di.telegram_bot_api.download_file.return_value = b"\xFF\xD8\xFF\xE0fake-jpeg"
        # noinspection PyPropertyAccess
        self.mock_di.attachment_storage = MagicMock()
        self.mock_di.attachment_storage.put.side_effect = lambda metadata, content: f"s3://the-agent/{metadata.uri}"
        self.mock_di.attachment_storage.owns_uri.side_effect = lambda uri: bool(uri) and uri.startswith("s3://the-agent/")
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service = MagicMock()
        # noinspection PyPropertyAccess
        self.mock_di.telegram_domain_mapper = MagicMock(wraps = TelegramDomainMapper())
        self.resolver = TelegramChatInboundService(self.mock_di)

    def tearDown(self):
        self.sql.end_session()

    def test_ingest_update_empty(self):
        result = self.resolver.ingest_update(Update(update_id = 1))

        self.assertIsNone(result)

    def test_ingest_message_no_author(self):
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 10,
            date = int(datetime.now().timestamp()),
            text = "This is a message",
        )

        result = self.resolver.ingest_message(message)

        self.assertIsNone(result.author)
        self.assertEqual(result.chat.external_id, "1")
        self.assertEqual(result.message.message_id, "10")
        self.assertIsNone(result.message.author_id)
        self.assertEqual(result.attachments, [])
        self.assertEqual(result.raw_message_text, "This is a message")

    def test_ingest_message_ignores_unsupported_anonymous_service_message(self):
        message = Message(
            chat = Chat(id = -1001474547339, type = "supergroup", title = "Hot Fintech Tips"),
            message_id = 104648,
            date = int(datetime.now().timestamp()),
            **{
                "from": TelegramUser(
                    id = 1087968824,
                    first_name = "Group",
                    username = "GroupAnonymousBot",
                    is_bot = True,
                ),
            },
        )

        result = self.resolver.ingest_message(message)

        self.assertIsNone(result)
        self.mock_di.telegram_domain_mapper.map_chat.assert_not_called()
        self.mock_di.telegram_domain_mapper.map_author.assert_not_called()
        self.mock_di.chat_membership_service.ensure_for_inbound.assert_not_called()

    def test_ingest_message_no_author_with_attachment_raises(self):
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 10,
            date = int(datetime.now().timestamp()),
            document = Document(file_id = "e1", file_unique_id = "u1", mime_type = "image/jpeg"),
        )

        with self.assertRaises(InternalError):
            self.resolver.ingest_message(message)

    def test_ingest_message_from_agent_skips_remote_attachments(self):
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 10,
            date = int(datetime.now().timestamp()),
            text = "This is a message",
            document = Document(file_id = "e1", file_unique_id = "u1", mime_type = "image/jpeg"),
            **{
                "from": TelegramUser(
                    id = self.agent_user.telegram_user_id,
                    first_name = self.agent_user.full_name,
                    username = self.agent_user.telegram_username,
                    is_bot = True,
                ),
            },
        )
        original_save = self.mock_di.chat_message_repo.save
        self.mock_di.chat_message_repo.save = Mock(wraps = original_save)

        result = self.resolver.ingest_message(message)

        assert result.author is not None
        self.assertEqual(result.author.telegram_user_id, self.agent_user.telegram_user_id)
        self.assertIsNone(result.author.telegram_chat_id)
        self.assertEqual(result.attachments, [])
        self.mock_di.telegram_domain_mapper.map_attachments.assert_not_called()
        self.mock_di.telegram_bot_api.download_file.assert_not_called()
        self.mock_di.chat_membership_service.ensure_for_inbound.assert_not_called()
        self.mock_di.chat_message_repo.save.assert_called_once()

    def test_ingest_message_with_attachment_uses_local_attachment_id(self):
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 10,
            date = int(datetime.now().timestamp()),
            caption = "This is a message",
            document = Document(file_id = "e1", file_unique_id = "u1", mime_type = "image/jpeg"),
            **{
                "from": TelegramUser(
                    id = 1,
                    first_name = "New User",
                    username = "username",
                    is_bot = False,
                ),
            },
        )
        original_save = self.mock_di.chat_message_repo.save
        self.mock_di.chat_message_repo.save = Mock(wraps = original_save)

        result = self.resolver.ingest_message(message)

        assert result.author is not None
        attachment_id = generate_deterministic_short_uuid("e1")
        self.assertEqual(result.attachments[0].id, attachment_id)
        self.assertEqual(result.attachments[0].message_id, "10")
        self.assertEqual(result.attachments[0].chat_id, result.chat.chat_id)
        self.assertEqual(result.attachments[0].uploader_user_id, result.author.id)
        self.assertIn(f"📎 [ {attachment_id} (image/jpeg) ]", result.message.text)
        self.assertEqual(result.raw_message_text, "This is a message")
        mapped_message = self.mock_di.telegram_domain_mapper.map_message.call_args.args[0]
        self.assertIs(mapped_message, message)
        self.assertNotIn(attachment_id, result.raw_message_text)
        self.mock_di.chat_message_repo.save.assert_called_once()
        self.mock_di.chat_membership_service.ensure_for_inbound.assert_called_once_with(result.author, result.chat)

    def test_ingest_message_with_video_uses_download_path_and_preserves_missing_mime_type(self):
        self.mock_di.telegram_bot_api.download_file.return_value = b"\x00\x00\x00\x18ftypmp42"
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 10,
            date = int(datetime.now().timestamp()),
            caption = "Video caption",
            video = Video(
                file_id = "video1",
                file_unique_id = "unique-video",
                width = 1920,
                height = 1080,
                duration = 5,
            ),
            **{
                "from": TelegramUser(
                    id = 1,
                    first_name = "New User",
                    username = "username",
                    is_bot = False,
                ),
            },
        )

        result = self.resolver.ingest_message(message)

        self.assertEqual(result.raw_message_text, "Video caption")
        self.assertEqual(len(result.attachments), 1)
        self.assertEqual(result.attachments[0].external_id, "video1")
        self.assertIsNone(result.attachments[0].mime_type)
        self.mock_di.telegram_bot_api.download_file.assert_called_once_with("video1")

    def test_ingest_message_with_reply_uses_local_attachment_id(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        uploader = self.sql.user_repo().save(User(full_name = "Agent", telegram_user_id = 123))
        self.sql.chat_message_repo().save(
            ChatMessage(
                chat_id = chat.chat_id,
                message_id = "19",
                text = "Original caption\n\n📎 [ remote123 ]",
            ),
        )
        self.sql.chat_attachment_repo().save(
            ChatAttachment(
                id = "local123",
                chat_id = chat.chat_id,
                uploader_user_id = uploader.id,
                message_id = "19",
                mime_type = "image/png",
            ),
        )
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 20,
            date = int(datetime.now().timestamp()),
            text = "Please use this",
            reply_to_message = Message(
                chat = Chat(id = 1, type = "private"),
                message_id = 19,
                date = int(datetime.now().timestamp()),
            ),
            **{
                "from": TelegramUser(id = 1, first_name = "New User", username = "username", is_bot = False),
            },
        )

        result = self.resolver.ingest_message(message)

        self.assertIn(">>>> Original caption", result.message.text)
        self.assertIn(">>>> 📎 [ local123 (image/png) ]", result.message.text)
        self.assertIn("Please use this", result.message.text)
        self.assertNotIn("remote123", result.message.text)

    def test_ingest_message_formats_native_quote_outside_mapper(self):
        message = Message(
            chat = Chat(id = 1, type = "private"),
            message_id = 20,
            date = int(datetime.now().timestamp()),
            text = "Current message",
            quote = TextQuote(text = "Selected quote", position = 0),
            **{
                "from": TelegramUser(id = 1, first_name = "New User", username = "username", is_bot = False),
            },
        )

        result = self.resolver.ingest_message(message)

        self.assertEqual(result.raw_message_text, "Current message")
        self.assertEqual(result.message.text, ">> Selected quote\n\nCurrent message")

    def test_store_author_none(self):
        result = self.resolver.store_author(None)
        self.assertIsNone(result)

    def test_store_author_new(self):
        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "New User",
            telegram_chat_id = "c1",
        )

        result = self.resolver.store_author(mapped_data)
        saved_user = self.sql.user_repo().get_by_telegram_user_id(mapped_data.telegram_user_id or -1)

        assert result is not None
        self.assertEqual(result, saved_user)
        self.assertIsNotNone(result.id)
        self.assertEqual(result.full_name, mapped_data.full_name)
        self.assertEqual(result.telegram_username, mapped_data.telegram_username)
        self.assertEqual(result.telegram_chat_id, mapped_data.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, mapped_data.telegram_user_id)
        self.assertIsNone(result.open_ai_key)
        self.assertEqual(result.group, UserDB.Group.standard)
        self.assertEqual(result.created_at, datetime.now().date())

    def test_store_author_by_username(self):
        existing_user_data = User(
            telegram_user_id = None,
            telegram_username = "unique_username",
            full_name = "Existing User",
        )
        existing_user = self.sql.user_repo().save(existing_user_data)

        mapped_data = UserRemoteData(
            telegram_user_id = None,
            telegram_username = "unique_username",
            full_name = "Updated User",
            telegram_chat_id = "c1",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None
        saved_user = self.sql.user_repo().get(result.id)

        assert result is not None
        self.assertEqual(result, saved_user)
        self.assertEqual(result.id, existing_user.id)
        # Should preserve existing name when DB has a value, even if platform sends a new one
        self.assertEqual(result.full_name, existing_user.full_name)
        self.assertEqual(result.telegram_username, mapped_data.telegram_username)
        self.assertEqual(result.telegram_chat_id, mapped_data.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, existing_user.telegram_user_id)
        self.assertEqual(result.open_ai_key, existing_user.open_ai_key)
        self.assertEqual(result.group, existing_user.group)
        self.assertEqual(result.created_at, existing_user.created_at)

    @patch("features.users.user_repo.UserRepository.count")
    def test_store_author_user_limit_reached_creates_waitlisted_user(self, mock_count):
        mock_count.return_value = config.max_users  # reach maximum immediately
        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "New User",
            telegram_chat_id = "c1",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None
        self.assertTrue(result.is_on_waitlist)
        self.assertFalse(result.is_invited_to_start)
        self.assertFalse(result.are_policies_accepted)
        mock_count.assert_called_once()

    def test_store_author_existing(self):
        existing_user_data = User(
            telegram_user_id = 1,
            full_name = "Existing User",
            telegram_chat_id = "c1",
            open_ai_key = SecretStr("sk-key"),
            anthropic_key = SecretStr("sk-key"),
            perplexity_key = SecretStr("sk-key"),
            replicate_key = SecretStr("sk-key"),
            rapid_api_key = SecretStr("sk-key"),
            coinmarketcap_key = SecretStr("sk-key"),
            twelve_data_api_key = SecretStr("sk-key"),
            x_key = SecretStr("sk-key"),
            x_ai_key = SecretStr("sk-key"),
            about_me = SecretStr("Personal info about me"),
            custom_prompt = SecretStr("Custom instructions to preserve"),
            credit_balance = 123.45,
            group = UserDB.Group.developer,
            # Add all tool choice fields to test preservation
            tool_choice_chat = "openai",
            tool_choice_reasoning = "anthropic",
            tool_choice_copywriting = "perplexity",
            tool_choice_vision = "openai",
            tool_choice_hearing = "openai",
            tool_choice_images_gen = "replicate",
            tool_choice_videos_gen = "prunaai/p-video",
            tool_choice_images_edit = "replicate",
            tool_choice_search = "perplexity",
            tool_choice_embedding = "openai",
            tool_choice_api_fiat_exchange = "rapidapi",
            tool_choice_api_crypto_exchange = "coinmarketcap",
            tool_choice_api_stock_quote = "twelve-data",
            tool_choice_api_twitter = "rapidapi",
        )
        existing_user = self.sql.user_repo().save(existing_user_data)

        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "Updated User",
            telegram_chat_id = "c2",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None

        saved_user = self.sql.user_repo().get(result.id)

        self.assertEqual(result, saved_user)
        self.assertEqual(result.id, existing_user.id)
        # Should preserve existing name when DB has a value, even if platform sends a new one
        self.assertEqual(result.full_name, existing_user.full_name)
        self.assertEqual(result.telegram_username, mapped_data.telegram_username)
        self.assertEqual(result.telegram_chat_id, existing_user.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, mapped_data.telegram_user_id)
        self.assertEqual(result.open_ai_key, existing_user.open_ai_key)
        self.assertEqual(result.anthropic_key, existing_user.anthropic_key)
        self.assertEqual(result.perplexity_key, existing_user.perplexity_key)
        self.assertEqual(result.replicate_key, existing_user.replicate_key)
        self.assertEqual(result.rapid_api_key, existing_user.rapid_api_key)
        self.assertEqual(result.coinmarketcap_key, existing_user.coinmarketcap_key)
        self.assertEqual(result.twelve_data_api_key, existing_user.twelve_data_api_key)
        self.assertEqual(result.x_key, existing_user.x_key)
        self.assertEqual(result.x_ai_key, existing_user.x_ai_key)
        self.assertEqual(result.about_me, existing_user.about_me)
        self.assertEqual(result.custom_prompt, existing_user.custom_prompt)
        self.assertEqual(result.credit_balance, existing_user.credit_balance)
        self.assertEqual(result.group, existing_user.group)
        self.assertEqual(result.created_at, existing_user.created_at)

        # Verify all tool choice fields are preserved from existing user
        self.assertEqual(result.tool_choice_chat, existing_user.tool_choice_chat)
        self.assertEqual(result.tool_choice_reasoning, existing_user.tool_choice_reasoning)
        self.assertEqual(result.tool_choice_copywriting, existing_user.tool_choice_copywriting)
        self.assertEqual(result.tool_choice_vision, existing_user.tool_choice_vision)
        self.assertEqual(result.tool_choice_hearing, existing_user.tool_choice_hearing)
        self.assertEqual(result.tool_choice_images_gen, existing_user.tool_choice_images_gen)
        self.assertEqual(result.tool_choice_videos_gen, existing_user.tool_choice_videos_gen)
        self.assertEqual(result.tool_choice_images_edit, existing_user.tool_choice_images_edit)
        self.assertEqual(result.tool_choice_search, existing_user.tool_choice_search)
        self.assertEqual(result.tool_choice_embedding, existing_user.tool_choice_embedding)
        self.assertEqual(result.tool_choice_api_fiat_exchange, existing_user.tool_choice_api_fiat_exchange)
        self.assertEqual(result.tool_choice_api_crypto_exchange, existing_user.tool_choice_api_crypto_exchange)
        self.assertEqual(result.tool_choice_api_stock_quote, existing_user.tool_choice_api_stock_quote)
        self.assertEqual(result.tool_choice_api_twitter, existing_user.tool_choice_api_twitter)

    def test_store_author_preserves_name_when_empty(self):
        existing_user_data = User(
            telegram_user_id = 1,
            full_name = "Existing User",
            telegram_chat_id = "c1",
        )
        existing_user = self.sql.user_repo().save(existing_user_data)

        # Test with None full_name
        mapped_data_none = UserRemoteData(
            telegram_user_id = 1,
            full_name = None,
            telegram_chat_id = "c2",
        )

        result = self.resolver.store_author(mapped_data_none)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name
        self.assertEqual(result.telegram_chat_id, existing_user.telegram_chat_id)

        # Test with empty string full_name
        mapped_data_empty = UserRemoteData(
            telegram_user_id = 1,
            full_name = "",
            telegram_chat_id = "c3",
        )

        result = self.resolver.store_author(mapped_data_empty)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name
        self.assertEqual(result.telegram_chat_id, existing_user.telegram_chat_id)

    def test_store_message_new(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        mapped_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "Raw message",
        )
        formatted_text = "Formatted message"

        result = self.resolver.store_message(mapped_data, formatted_text, chat.chat_id, None)
        saved_message = self.sql.chat_message_repo().get(chat.chat_id, mapped_data.message_id)

        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertIsNone(result.author_id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, formatted_text)
        self.assertEqual(mapped_data.text, "Raw message")

    def test_store_message_with_existing(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        old_message_data = ChatMessage(
            chat_id = chat.chat_id,
            message_id = "m1",
            author_id = None,
            sent_at = datetime.now() - timedelta(days = 1),
            text = "Old message",
        )
        self.sql.chat_message_repo().save(old_message_data)

        new_author = self.sql.user_repo().save(User(full_name = "First Last", telegram_chat_id = "c1"))
        mapped_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "Raw updated message",
        )
        formatted_text = "Formatted updated message"

        result = self.resolver.store_message(mapped_data, formatted_text, chat.chat_id, new_author.id)
        saved_message = self.sql.chat_message_repo().get(chat.chat_id, mapped_data.message_id)

        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.author_id, new_author.id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, formatted_text)
        self.assertEqual(mapped_data.text, "Raw updated message")

    def test_store_message_preserves_existing_author_when_unresolved(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        author = self.sql.user_repo().save(User(
            full_name = "Existing Author",
            telegram_user_id = 1,
        ))
        self.sql.chat_message_repo().save(ChatMessage(
            chat_id = chat.chat_id,
            message_id = "m1",
            author_id = author.id,
            sent_at = datetime.now() - timedelta(days = 1),
            text = "Old message",
        ))
        mapped_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "Raw edited message",
        )
        formatted_text = "Formatted edited message"

        result = self.resolver.store_message(mapped_data, formatted_text, chat.chat_id, None)

        self.assertEqual(result.author_id, author.id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, formatted_text)
        self.assertEqual(mapped_data.text, "Raw edited message")

    def test_store_attachment_new(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        uploader = self.sql.user_repo().save(User(full_name = "Uploader", telegram_user_id = 123))
        self.sql.chat_message_repo().save(ChatMessage(chat_id = chat.chat_id, message_id = "m1", text = "x"))
        mapped_data = ChatAttachmentRemoteData(
            external_id = "e1",
            message_id = "m1",
            last_url = "path/to/file.jpg",
            extension = "jpg",
            mime_type = "image/jpeg",
        )

        result = self.resolver.store_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.sql.chat_attachment_repo().get_by_external_id(chat.chat_id, mapped_data.external_id)

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, generate_deterministic_short_uuid(mapped_data.external_id))
        self.assertEqual(result.external_id, mapped_data.external_id)
        self.assertEqual(result.uploader_user_id, uploader.id)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.size, len(self.mock_di.telegram_bot_api.download_file.return_value))
        self.assertTrue(result.last_url.startswith(f"s3://{config.s3_bucket}/chats/"))
        self.assertEqual(result.extension, "jpg")
        self.assertEqual(result.mime_type, "image/jpeg")

    def test_store_attachment_existing(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        self.sql.chat_message_repo().save(ChatMessage(chat_id = chat.chat_id, message_id = "m1", text = "x"))
        uploader = self.sql.user_repo().save(User(full_name = "Uploader", telegram_user_id = 123))
        old_attachment_data = ChatAttachment(
            id = "i1",
            external_id = "e1",
            chat_id = chat.chat_id,
            uploader_user_id = uploader.id,
            message_id = "m1",
            size = 1,
            last_url = f"s3://{config.s3_bucket}/chats/{chat.chat_id}/attachments/i1.jpg",
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        self.sql.chat_attachment_repo().save(old_attachment_data)

        mapped_data = ChatAttachmentRemoteData(external_id = "e1", message_id = "m1")
        result = self.resolver.store_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.sql.chat_attachment_repo().get("i1")

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, old_attachment_data.id)
        self.assertEqual(result.uploader_user_id, old_attachment_data.uploader_user_id)
        self.assertEqual(result.chat_id, old_attachment_data.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.size, old_attachment_data.size)
        self.assertEqual(result.last_url, old_attachment_data.last_url)
        self.assertEqual(result.extension, old_attachment_data.extension)
        self.assertEqual(result.mime_type, old_attachment_data.mime_type)
