import unittest
from datetime import date
from unittest.mock import Mock, patch
from uuid import UUID

from db.sql_util import SQLUtil
from langchain_core.messages import AIMessage

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.telegram.model.update import Update
from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.chat.telegram.telegram_update_responder import respond_to_update


class TelegramUpdateResponderTest(unittest.TestCase):

    sql: SQLUtil
    update: Update
    di: Mock
    mock_sleep: Mock

    def setUp(self):
        # create all the mocks
        self.sql = SQLUtil()
        self.update = Mock(spec = Update)

        patcher_sleep = patch("features.chat.telegram.telegram_update_responder.sleep")
        self.addCleanup(patcher_sleep.stop)
        self.mock_sleep = patcher_sleep.start()

        # mock the DI container
        patcher_di = patch("features.chat.telegram.telegram_update_responder.DI")
        self.addCleanup(patcher_di.stop)
        self.di = patcher_di.start().return_value

        self.di.access_token_resolver.get_access_token_for_tool.return_value = "dummy_token"

        # patch all dependencies in the correct namespace where they are used in telegram_update_responder
        patcher_get_detached_session = patch("features.chat.telegram.telegram_update_responder.get_detached_session")
        self.addCleanup(patcher_get_detached_session.stop)
        self.mock_get_detached_session = patcher_get_detached_session.start()
        self.mock_get_detached_session.return_value.__enter__.return_value = self.sql.start_session()

        # patch the DI's chat_agent and telegram_bot_sdk mocks for use in tests
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")
        self.di.telegram_bot_sdk.send_text_message = Mock()

    def tearDown(self):
        self.sql.end_session()

    def test_successful_response(self):
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")

        self.di.telegram_domain_mapper.map_update.return_value = Mock(
            spec = TelegramDomainMapper.Result,
            message = Mock(spec = ChatMessage, message_id = "test-message-id", text = "Test message text"),
        )

        author_db = UserDB(
            id = UUID(int = 1),
            telegram_username = "test_user",
            full_name = "Test User",
            telegram_user_id = 1,
            connect_key = "TG-USER-KEY1",
            group = UserDB.Group.standard,
            created_at = date.today(),
            telegram_chat_id = "123",
            credit_balance = 0.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )

        self.di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            chat = ChatConfig(
                chat_id = UUID(int = 123),
                external_id = "123",
                language_name = "English",
                language_iso_code = "en",
                title = "Test Chat",
                is_private = False,
                reply_chance_percent = 100,
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
            author = User.model_validate(author_db),
        )
        self.di.chat_message_repo.get_latest_by_chat.return_value = []
        self.di.user_crud.get.return_value = author_db  # Return author for all calls

        self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = [
            Mock(chat_id = "123", text = "Test response"),
        ]

        result = respond_to_update(self.update)

        self.assertTrue(result)
        # Agent user creation logic was removed, so user_crud.save should not be called
        self.di.chat_agent.return_value.execute.assert_called_once()
        self.di.telegram_bot_sdk.send_text_message.assert_called_once_with("123", "Test response")
        self.mock_sleep.assert_called_once_with(0.1)

    def test_reaction_response(self):
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "👍")
        self.di.telegram_domain_mapper.map_update.return_value = Mock(
            spec = TelegramDomainMapper.Result,
            message = Mock(spec = ChatMessage, message_id = "test-message-id", text = "Test message text"),
        )
        self.di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            chat = ChatConfig(
                chat_id = UUID(int = 123),
                external_id = "123",
                language_name = "English",
                language_iso_code = "en",
                title = "Test Chat",
                is_private = False,
                reply_chance_percent = 100,
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
            author = Mock(spec = User, id = UUID(int = 1)),
            message = Mock(spec = ChatMessage, message_id = "test-message-id"),
        )

        result = respond_to_update(self.update)

        self.assertTrue(result)
        self.di.platform_bot_sdk.return_value.set_reaction.assert_called_once_with("123", "test-message-id", "👍")
        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.telegram_bot_sdk.send_text_message.assert_not_called()
        self.mock_sleep.assert_not_called()
        saved_message = self.di.chat_message_repo.save.call_args.args[0]
        self.assertIsInstance(saved_message, ChatMessage)
        self.assertEqual(saved_message.message_id, "reaction:test-message-id")
        self.assertEqual(saved_message.text, "<reaction>👍</reaction>")

    def test_reaction_response_failure(self):
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "👍")
        self.di.platform_bot_sdk.return_value.set_reaction.side_effect = Exception("Reaction failed")
        self.di.telegram_domain_mapper.map_update.return_value = Mock(
            spec = TelegramDomainMapper.Result,
            message = Mock(spec = ChatMessage, message_id = "test-message-id", text = "Test message text"),
        )
        self.di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            chat = ChatConfig(
                chat_id = UUID(int = 123),
                external_id = "123",
                language_name = "English",
                language_iso_code = "en",
                title = "Test Chat",
                is_private = False,
                reply_chance_percent = 100,
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
            author = Mock(spec = User, id = UUID(int = 1)),
            message = Mock(spec = ChatMessage, message_id = "test-message-id"),
        )

        result = respond_to_update(self.update)

        self.assertTrue(result)
        self.di.platform_bot_sdk.return_value.set_reaction.assert_called_once_with("123", "test-message-id", "👍")
        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.telegram_bot_sdk.send_text_message.assert_not_called()
        self.mock_sleep.assert_not_called()
        saved_message = self.di.chat_message_repo.save.call_args.args[0]
        self.assertIsInstance(saved_message, ChatMessage)
        self.assertEqual(saved_message.message_id, "reaction:test-message-id")
        self.assertEqual(saved_message.text, "<reaction>👍</reaction>")

    def test_empty_response(self):
        self.di.telegram_domain_mapper.map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
        self.di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            chat = Mock(spec = ChatConfig, chat_id = "123"),
            author = Mock(spec = User, id = UUID(int = 1)),
        )
        self.di.chat_message_repo.get_latest_by_chat.return_value = []
        self.di.chat_agent.return_value.execute.return_value = Mock(content = "")

        result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.telegram_bot_sdk.send_text_message.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_mapping_error(self):
        self.di.telegram_domain_mapper.map_update.return_value = None

        with patch("features.integrations.prompt_resolvers.simple_chat_error", return_value = "Mapping error"):
            self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = [
                Mock(chat_id = "123", text = "Mapping error"),
            ]
            result = respond_to_update(self.update)

        self.assertFalse(result)

        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.telegram_bot_sdk.send_text_message.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_no_author_returns_false(self):
        self.di.telegram_domain_mapper.map_update.return_value = Mock(
            spec = TelegramDomainMapper.Result,
            message = Mock(spec = ChatMessage, message_id = "test-message-id", text = "Test message text"),
        )
        self.di.telegram_data_resolver.resolve.return_value = Mock(
            spec = TelegramDataResolver.Result,
            chat = Mock(spec = ChatConfig, chat_id = "123"),
            author = None,
        )

        result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.chat_agent.assert_not_called()
        self.di.telegram_bot_sdk.send_text_message.assert_not_called()

    def test_general_exception(self):
        from collections import namedtuple
        with patch("features.chat.telegram.telegram_update_responder.silent", lambda f: f):
            self.di.telegram_domain_mapper.map_update.return_value = Mock(spec = TelegramDomainMapper.Result)
            resolved_domain_data_mock = Mock(
                spec = TelegramDataResolver.Result,
                chat = Mock(spec = ChatConfig, chat_id = UUID(int = 123), external_id = "123"),
                author = Mock(spec = User, id = UUID(int = 1)),
            )
            self.di.telegram_data_resolver.resolve.return_value = resolved_domain_data_mock

            error_message = "Test error"
            ErrorMsg = namedtuple("ErrorMsg", ["chat_id", "text"])
            error_response = [ErrorMsg(chat_id = "123", text = "Error response")]
            # Raise exception during message fetching, after resolved_domain_data is set
            self.di.chat_message_repo.get_latest_by_chat.side_effect = Exception(error_message)
            self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = error_response
            self.di.telegram_bot_sdk.send_text_message = Mock()

            with patch("features.integrations.prompt_resolvers.simple_chat_error") as mock_error:
                mock_error.return_value = "Error response"
                result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.telegram_bot_sdk.send_text_message.assert_called_once_with("123", "Error response")
        self.mock_sleep.assert_called_once_with(0.1)
        self.di.chat_message_repo.save.assert_not_called()
