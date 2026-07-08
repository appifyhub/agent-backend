import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_remote_data import ChatMessageAttachmentRemoteData
from features.chat.attachment.chat_message_attachment_service import ChatMessageAttachmentService
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.integrations.integrations import resolve_agent_user
from features.users.user import User
from features.users.user_remote_data import UserRemoteData
from util.config import config
from util.errors import InternalError
from util.functions import generate_deterministic_short_uuid


class TelegramDataResolverTest(unittest.TestCase):

    sql: SQLUtil
    mock_di: DI
    resolver: TelegramDataResolver

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
        self.mock_di.chat_message_attachment_repo = self.sql.chat_message_attachment_repo()
        # noinspection PyPropertyAccess
        self.mock_di.chat_message_attachment_service = ChatMessageAttachmentService(self.mock_di)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_api = MagicMock()
        # Ensure resolver uses a real SDK instance rather than an auto-created Mock
        # so that attachment refresh returns real models instead of Mock objects
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_sdk = TelegramBotSDK(self.mock_di)
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service = MagicMock()
        self.resolver = TelegramDataResolver(self.mock_di)

    def tearDown(self):
        self.sql.end_session()

    def test_resolve_no_author(self):
        chat_config_data = ChatConfigRemoteData(
            external_id = "c1",
            title = "Chat Title",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        message_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "This is a message",
        )
        mapping_result = TelegramDomainMapper.Result(
            chat = chat_config_data,
            author = None,
            message = message_data,
            attachments = [],
        )

        result = self.resolver.resolve(mapping_result)

        self.assertIsNone(result.author)
        self.assertEqual(result.chat.external_id, chat_config_data.external_id)
        self.assertEqual(result.chat.is_private, chat_config_data.is_private)
        self.assertIsNone(result.author)
        self.assertEqual(result.message.chat_id, result.chat.chat_id)
        self.assertEqual(result.message.message_id, message_data.message_id)
        self.assertIsNone(result.message.author_id)
        self.assertEqual(result.attachments, [])

    def test_resolve_no_author_with_attachment_raises(self):
        mapping_result = TelegramDomainMapper.Result(
            chat = ChatConfigRemoteData(
                external_id = "c1",
                title = "Chat Title",
                is_private = True,
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
            author = None,
            message = ChatMessageRemoteData(
                message_id = "m1",
                sent_at = datetime.now(),
                text = "This is a message",
            ),
            attachments = [
                ChatMessageAttachmentRemoteData(
                    external_id = "e1",
                    message_id = "m1",
                    mime_type = "image/jpeg",
                ),
            ],
        )

        with self.assertRaises(InternalError):
            self.resolver.resolve(mapping_result)

    def test_resolve_with_author_bot(self):
        chat_config_data = ChatConfigRemoteData(
            external_id = "c1",
            title = "Chat Title",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        author_data = UserRemoteData(
            telegram_username = self.agent_user.telegram_username,
            telegram_chat_id = "c1",
            telegram_user_id = self.agent_user.telegram_user_id,
            full_name = self.agent_user.full_name,
        )
        message_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "This is a message",
        )
        attachment_data = ChatMessageAttachmentRemoteData(
            external_id = "e1",
            message_id = message_data.message_id,
            last_url = "path/to/file.jpg",
            last_url_until = self.valid_url_timestamp(),
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        mapping_result = TelegramDomainMapper.Result(
            chat = chat_config_data,
            author = author_data,
            message = message_data,
            attachments = [attachment_data],
        )

        result = self.resolver.resolve(mapping_result)

        assert result.author is not None
        self.assertIsNotNone(result.author.id)
        self.assertEqual(result.author.telegram_user_id, author_data.telegram_user_id)
        self.assertIsNone(result.author.telegram_chat_id)
        self.assertEqual(result.chat.external_id, chat_config_data.external_id)
        self.assertEqual(result.chat.is_private, chat_config_data.is_private)
        self.assertEqual(result.message.chat_id, result.chat.chat_id)
        self.assertEqual(result.message.message_id, message_data.message_id)
        self.assertIsNotNone(result.message.author_id)
        self.assertEqual(result.attachments[0].id, generate_deterministic_short_uuid(attachment_data.external_id))
        self.assertEqual(result.attachments[0].external_id, attachment_data.external_id)
        self.assertEqual(result.attachments[0].message_id, attachment_data.message_id)
        self.assertEqual(result.attachments[0].chat_id, result.chat.chat_id)
        self.assertEqual(result.attachments[0].uploader_user_id, result.author.id)
        self.mock_di.chat_membership_service.sync.assert_not_called()

    def test_resolve_with_author_normal(self):
        chat_config_data = ChatConfigRemoteData(
            external_id = "c1",
            title = "Chat Title",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        author_data = UserRemoteData(
            telegram_username = "username",
            telegram_chat_id = "c1",
            telegram_user_id = 1,
            full_name = "New User",
        )
        message_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "This is a message",
        )
        attachment_data = ChatMessageAttachmentRemoteData(
            external_id = "e1",
            message_id = message_data.message_id,
            last_url = "path/to/file.jpg",
            last_url_until = self.valid_url_timestamp(),
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        mapping_result = TelegramDomainMapper.Result(
            chat = chat_config_data,
            author = author_data,
            message = message_data,
            attachments = [attachment_data],
        )

        result = self.resolver.resolve(mapping_result)

        assert result.author is not None
        self.assertIsNotNone(result.author.id)
        self.assertEqual(result.author.telegram_user_id, author_data.telegram_user_id)
        self.assertEqual(result.author.telegram_chat_id, chat_config_data.external_id)
        self.assertEqual(result.chat.external_id, chat_config_data.external_id)
        self.assertEqual(result.chat.is_private, chat_config_data.is_private)
        self.assertEqual(result.message.chat_id, result.chat.chat_id)
        self.assertEqual(result.message.message_id, message_data.message_id)
        self.assertIsNotNone(result.message.author_id)
        self.assertEqual(result.attachments[0].id, generate_deterministic_short_uuid(attachment_data.external_id))
        self.assertEqual(result.attachments[0].external_id, attachment_data.external_id)
        self.assertEqual(result.attachments[0].message_id, attachment_data.message_id)
        self.assertEqual(result.attachments[0].chat_id, result.chat.chat_id)
        self.assertEqual(result.attachments[0].uploader_user_id, result.author.id)
        self.mock_di.chat_membership_service.sync.assert_called_once()

    def test_resolve_author_none(self):
        result = self.resolver.resolve_author(None)
        self.assertIsNone(result)

    def test_resolve_author_new(self):
        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "New User",
            telegram_chat_id = "c1",
        )

        result = self.resolver.resolve_author(mapped_data)
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

    def test_resolve_author_by_username(self):
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

        result = self.resolver.resolve_author(mapped_data)
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
    def test_resolve_author_user_limit_reached_creates_waitlisted_user(self, mock_count):
        mock_count.return_value = config.max_users  # reach maximum immediately
        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "New User",
            telegram_chat_id = "c1",
        )

        result = self.resolver.resolve_author(mapped_data)
        assert result is not None
        self.assertTrue(result.is_on_waitlist)
        self.assertFalse(result.is_invited_to_start)
        self.assertFalse(result.are_policies_accepted)
        mock_count.assert_called_once()

    def test_resolve_author_existing(self):
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
            tool_choice_images_edit = "replicate",
            tool_choice_search = "perplexity",
            tool_choice_embedding = "openai",
            tool_choice_api_fiat_exchange = "rapidapi",
            tool_choice_api_crypto_exchange = "coinmarketcap",
            tool_choice_api_twitter = "rapidapi",
        )
        existing_user = self.sql.user_repo().save(existing_user_data)

        mapped_data = UserRemoteData(
            telegram_user_id = 1,
            full_name = "Updated User",
            telegram_chat_id = "c2",
        )

        result = self.resolver.resolve_author(mapped_data)
        assert result is not None

        saved_user = self.sql.user_repo().get(result.id)

        self.assertEqual(result, saved_user)
        self.assertEqual(result.id, existing_user.id)
        # Should preserve existing name when DB has a value, even if platform sends a new one
        self.assertEqual(result.full_name, existing_user.full_name)
        self.assertEqual(result.telegram_username, mapped_data.telegram_username)
        self.assertEqual(result.telegram_chat_id, mapped_data.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, mapped_data.telegram_user_id)
        self.assertEqual(result.open_ai_key, existing_user.open_ai_key)
        self.assertEqual(result.anthropic_key, existing_user.anthropic_key)
        self.assertEqual(result.perplexity_key, existing_user.perplexity_key)
        self.assertEqual(result.replicate_key, existing_user.replicate_key)
        self.assertEqual(result.rapid_api_key, existing_user.rapid_api_key)
        self.assertEqual(result.coinmarketcap_key, existing_user.coinmarketcap_key)
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
        self.assertEqual(result.tool_choice_images_edit, existing_user.tool_choice_images_edit)
        self.assertEqual(result.tool_choice_search, existing_user.tool_choice_search)
        self.assertEqual(result.tool_choice_embedding, existing_user.tool_choice_embedding)
        self.assertEqual(result.tool_choice_api_fiat_exchange, existing_user.tool_choice_api_fiat_exchange)
        self.assertEqual(result.tool_choice_api_crypto_exchange, existing_user.tool_choice_api_crypto_exchange)
        self.assertEqual(result.tool_choice_api_twitter, existing_user.tool_choice_api_twitter)

    def test_resolve_author_preserves_name_when_empty(self):
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

        result = self.resolver.resolve_author(mapped_data_none)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name

        # Test with empty string full_name
        mapped_data_empty = UserRemoteData(
            telegram_user_id = 1,
            full_name = "",
            telegram_chat_id = "c3",
        )

        result = self.resolver.resolve_author(mapped_data_empty)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name

    def test_resolve_chat_message_new(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        mapped_data = ChatMessageRemoteData(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "This is a message",
        )

        result = self.resolver.resolve_chat_message(mapped_data, chat.chat_id, None)
        saved_message = self.sql.chat_message_repo().get(chat.chat_id, mapped_data.message_id)

        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertIsNone(result.author_id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, mapped_data.text)

    def test_resolve_chat_message_with_existing(self):
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
            text = "Updated message",
        )

        result = self.resolver.resolve_chat_message(mapped_data, chat.chat_id, new_author.id)
        saved_message = self.sql.chat_message_repo().get(chat.chat_id, mapped_data.message_id)

        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.author_id, new_author.id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, mapped_data.text)

    def test_resolve_chat_message_preserves_existing_author_when_unresolved(self):
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
            text = "Edited message",
        )

        result = self.resolver.resolve_chat_message(mapped_data, chat.chat_id, None)

        self.assertEqual(result.author_id, author.id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, mapped_data.text)

    def test_resolve_chat_message_attachment_new(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        uploader = self.sql.user_repo().save(User(full_name = "Uploader", telegram_user_id = 123))
        self.sql.chat_message_repo().save(ChatMessage(chat_id = chat.chat_id, message_id = "m1", text = "x"))
        mapped_data = ChatMessageAttachmentRemoteData(
            external_id = "e1",
            message_id = "m1",
            last_url = "path/to/file.jpg",
            last_url_until = self.valid_url_timestamp(),
            extension = "jpg",
            mime_type = "image/jpeg",
        )

        result = self.resolver.resolve_chat_message_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.sql.chat_message_attachment_repo().get_by_external_id(chat.chat_id, mapped_data.external_id)

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, generate_deterministic_short_uuid(mapped_data.external_id))
        self.assertEqual(result.external_id, mapped_data.external_id)
        self.assertEqual(result.uploader_user_id, uploader.id)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.size, mapped_data.size)
        self.assertEqual(result.last_url, mapped_data.last_url)
        self.assertEqual(result.last_url_until, mapped_data.last_url_until)
        self.assertEqual(result.extension, mapped_data.extension)
        self.assertEqual(result.mime_type, mapped_data.mime_type)

    def test_resolve_chat_message_attachment_existing(self):
        chat = self.sql.chat_config_repo().save(
            ChatConfig(external_id = "c1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        self.sql.chat_message_repo().save(ChatMessage(chat_id = chat.chat_id, message_id = "m1", text = "x"))
        uploader = self.sql.user_repo().save(User(full_name = "Uploader", telegram_user_id = 123))
        old_attachment_data = ChatMessageAttachment(
            id = "i1",
            external_id = "e1",
            chat_id = chat.chat_id,
            uploader_user_id = uploader.id,
            message_id = "m1",
            size = 1,
            last_url = "path/to/file.jpg",
            last_url_until = self.valid_url_timestamp(),
            extension = "jpg",
            mime_type = "image/jpeg",
        )
        self.sql.chat_message_attachment_repo().save(old_attachment_data)

        mapped_data = ChatMessageAttachmentRemoteData(external_id = "e1", message_id = "m1")
        result = self.resolver.resolve_chat_message_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.sql.chat_message_attachment_repo().get("i1")

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, old_attachment_data.id)
        self.assertEqual(result.uploader_user_id, old_attachment_data.uploader_user_id)
        self.assertEqual(result.chat_id, old_attachment_data.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.size, old_attachment_data.size)
        self.assertEqual(result.last_url, old_attachment_data.last_url)
        self.assertEqual(result.last_url_until, old_attachment_data.last_url_until)
        self.assertEqual(result.extension, old_attachment_data.extension)
        self.assertEqual(result.mime_type, old_attachment_data.mime_type)

    @staticmethod
    def valid_url_timestamp():
        return int(datetime.now().timestamp()) + 10

    @staticmethod
    def expired_url_timestamp():
        return int(datetime.now().timestamp()) - 10
