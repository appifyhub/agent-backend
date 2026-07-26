import unittest
from collections import namedtuple
from datetime import date, datetime
from unittest.mock import Mock, patch
from uuid import UUID

from db.sql_util import SQLUtil
from langchain_core.messages import AIMessage

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from features.chat.config.chat_config import ChatConfig
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.whatsapp.model.update import Update
from features.chat.whatsapp.whatsapp_update_responder import respond_to_update
from features.users.user import User
from util.error_codes import PLATFORM_MAPPING_FAILED
from util.errors import ServiceError


class WhatsAppUpdateResponderTest(unittest.TestCase):

    sql: SQLUtil
    update: Update
    di: Mock
    mock_sleep: Mock

    def setUp(self):
        # create all the mocks
        self.sql = SQLUtil()
        self.update = Update(object = "whatsapp_business_account", entry = [])

        patcher_sleep = patch("features.chat.whatsapp.whatsapp_update_responder.sleep")
        self.addCleanup(patcher_sleep.stop)
        self.mock_sleep = patcher_sleep.start()

        # mock the DI container
        patcher_di = patch("features.chat.whatsapp.whatsapp_update_responder.DI")
        self.addCleanup(patcher_di.stop)
        self.di = patcher_di.start().return_value

        self.di.access_token_resolver.get_access_token_for_tool.return_value = "dummy_token"

        # patch all dependencies in the correct namespace where they are used in whatsapp_update_responder
        patcher_get_detached_session = patch("features.chat.whatsapp.whatsapp_update_responder.get_detached_session")
        self.addCleanup(patcher_get_detached_session.stop)
        self.mock_get_detached_session = patcher_get_detached_session.start()
        self.mock_get_detached_session.return_value.__enter__.return_value = self.sql.start_session()

        # patch the DI's chat_agent and whatsapp_bot_sdk mocks for use in tests
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")
        self.di.whatsapp_bot_sdk.send_text_message = Mock()

    def __resolved_result(
        self,
        chat_config: ChatConfig | None = None,
        author: User | None = None,
        message: ChatMessage | None = None,
        raw_message_text: str = "Test message text",
    ):
        return Mock(
            spec = IngestedChatMessage,
            chat = chat_config or ChatConfig(
                chat_id = UUID(int = 123),
                external_id = "123",
                language_name = "English",
                language_iso_code = "en",
                title = "Test Chat",
                is_private = False,
                reply_chance_percent = 100,
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_type = ChatConfigDB.ChatType.whatsapp,
            ),
            author = author,
            message = message or Mock(
                spec = ChatMessage,
                message_id = "test-message-id",
                sent_at = datetime.now(),
                text = "Stored message text",
            ),
            raw_message_text = raw_message_text,
        )

    def tearDown(self):
        self.sql.end_session()

    def test_successful_response(self):
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")

        author = User(
            id = UUID(int = 1),
            full_name = "Test User",
            whatsapp_user_id = "1",
            connect_key = "WA-USER-KEY1",
            group = UserDB.Group.standard,
            created_at = date.today(),
        )

        chat_config = ChatConfig(
            chat_id = UUID(int = 123),
            external_id = "123",
            language_name = "English",
            language_iso_code = "en",
            title = "Test Chat",
            is_private = False,
            reply_chance_percent = 100,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        resolved = self.__resolved_result(chat_config = chat_config, author = author)
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [resolved]
        self.di.chat_message_repo.get_latest_by_chat.return_value = []
        events = []

        def send_text_message(chat, text):
            events.append(f"send:{text}")

        def rollback_session():
            events.append("rollback")

        def sleep(delay):
            events.append("sleep")

        self.di.whatsapp_bot_sdk.send_text_message.side_effect = send_text_message
        self.di.rollback_db_session.side_effect = rollback_session
        self.mock_sleep.side_effect = sleep

        self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = [
            Mock(chat_id = "123", text = "Test response"),
        ]

        result = respond_to_update(self.update)

        self.assertTrue(result)
        self.di.whatsapp_chat_inbound_service.ingest_update.assert_called_once_with(self.update)
        self.di.chat_agent.assert_called_once_with(
            raw_last_message = "Test message text",
            last_message_id = "test-message-id",
            configured_tool = self.di.tool_choice_resolver.get_tool.return_value,
        )
        self.di.chat_agent.return_value.execute.assert_called_once()
        self.di.whatsapp_bot_sdk.send_text_message.assert_called_once_with(chat_config, "Test response")
        self.mock_sleep.assert_called_once_with(0.1)
        self.assertEqual(events, ["rollback", "send:Test response", "rollback", "sleep"])

    def test_reaction_response(self):
        self.di.chat_agent.return_value.execute.return_value = AIMessage(content = [
            {"type": "thinking", "thinking": "A reaction is appropriate"},
            {"type": "text", "text": "👍"},
        ])
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [
            self.__resolved_result(
                author = Mock(spec = User, id = UUID(int = 1)),
                message = Mock(
                    spec = ChatMessage,
                    message_id = "test-message-id",
                    sent_at = datetime.now(),
                    text = "Test message text",
                ),
            ),
        ]

        result = respond_to_update(self.update)

        self.assertTrue(result)
        self.di.platform_bot_sdk.return_value.set_reaction.assert_called_once_with("123", "test-message-id", "👍")
        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.mock_sleep.assert_not_called()
        self.di.whatsapp_bot_sdk.mark_as_read.assert_called_once_with("test-message-id")
        saved_message = self.di.chat_message_repo.save.call_args.args[0]
        self.assertIsInstance(saved_message, ChatMessage)
        self.assertEqual(saved_message.message_id, "reaction:test-message-id")
        self.assertEqual(saved_message.text, "<reaction>👍</reaction>")

    def test_reaction_response_failure(self):
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "👍")
        self.di.platform_bot_sdk.return_value.set_reaction.side_effect = Exception("Reaction failed")
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [
            self.__resolved_result(
                author = Mock(spec = User, id = UUID(int = 1)),
                message = Mock(
                    spec = ChatMessage,
                    message_id = "test-message-id",
                    sent_at = datetime.now(),
                    text = "Test message text",
                ),
            ),
        ]

        result = respond_to_update(self.update)

        self.assertTrue(result)
        self.di.platform_bot_sdk.return_value.set_reaction.assert_called_once_with("123", "test-message-id", "👍")
        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.mock_sleep.assert_not_called()
        self.di.whatsapp_bot_sdk.mark_as_read.assert_called_once_with("test-message-id")
        saved_message = self.di.chat_message_repo.save.call_args.args[0]
        self.assertIsInstance(saved_message, ChatMessage)
        self.assertEqual(saved_message.message_id, "reaction:test-message-id")
        self.assertEqual(saved_message.text, "<reaction>👍</reaction>")

    def test_empty_response(self):
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [
            self.__resolved_result(author = Mock(spec = User, id = UUID(int = 1))),
        ]
        self.di.chat_message_repo.get_latest_by_chat.return_value = []
        self.di.chat_agent.return_value.execute.return_value = Mock(content = "")

        result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_ingestion_error(self):
        raw_message = Mock(id = "raw-message-id", timestamp = "1")
        raw_message.from_ = "123"
        change = Mock(value = Mock(messages = [raw_message]))
        self.update = Mock(spec = Update, entry = [Mock(changes = [change])])
        self.di.whatsapp_chat_inbound_service.ingest_update.side_effect = Exception("Mapping error")

        with patch("features.integrations.prompt_resolvers.simple_chat_error", return_value = "Mapping error"):
            self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = [
                Mock(chat_id = "123", text = "Mapping error"),
            ]
            result = respond_to_update(self.update)

        self.assertFalse(result)

        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_not_called()
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.di.whatsapp_bot_sdk.set_reaction.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_empty_update_no_messages(self):
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = []

        result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.whatsapp_chat_inbound_service.ingest_update.assert_called_once_with(self.update)
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_mapping_failure_before_text_delivery_sends_no_error_message_or_reaction(self):
        resolved = self.__resolved_result(author = Mock(spec = User, id = UUID(int = 1)))
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [resolved]
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")
        self.di.chat_message_repo.get_latest_by_chat.return_value = []

        error = ServiceError(
            message = "Mapping failed",
            error_code = PLATFORM_MAPPING_FAILED,
            http_status = 500,
            emoji = "🧨",
        )
        self.di.domain_langchain_mapper.map_bot_message_to_storage.side_effect = error

        with patch("features.integrations.prompt_resolvers.simple_chat_error") as mock_error:
            result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.domain_langchain_mapper.map_bot_message_to_storage.assert_called_once_with(
            resolved.chat,
            self.di.chat_agent.return_value.execute.return_value,
        )
        mock_error.assert_not_called()
        self.di.whatsapp_bot_sdk.send_text_message.assert_not_called()
        self.di.platform_bot_sdk.return_value.set_reaction.assert_not_called()
        self.di.whatsapp_bot_sdk.set_reaction.assert_not_called()
        self.di.whatsapp_bot_sdk.mark_as_read.assert_not_called()
        self.mock_sleep.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_first_response_send_failure_sends_one_error_text_without_reaction_or_pre_failure_sleep(self):
        resolved = self.__resolved_result(author = Mock(spec = User, id = UUID(int = 1)))
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [resolved]
        self.di.chat_agent.return_value.execute.return_value = Mock(spec = AIMessage, content = "Test response")
        self.di.chat_message_repo.get_latest_by_chat.return_value = []

        error = ServiceError(
            message = "Test error",
            error_code = PLATFORM_MAPPING_FAILED,
            http_status = 500,
            emoji = "🧨",
        )
        ErrorMsg = namedtuple("ErrorMsg", ["chat_id", "text"])
        response = [ErrorMsg(chat_id = "123", text = "First response")]
        error_response = [ErrorMsg(chat_id = "123", text = "Error response")]
        self.di.domain_langchain_mapper.map_bot_message_to_storage.side_effect = [response, error_response]
        events = []

        def send_text_message(chat, text):
            events.append(f"send:{text}")
            if text == "First response":
                raise error

        def rollback_session():
            events.append("rollback")

        def sleep(delay):
            events.append("sleep")

        self.di.whatsapp_bot_sdk.send_text_message.side_effect = send_text_message
        self.di.rollback_db_session.side_effect = rollback_session
        self.mock_sleep.side_effect = sleep

        with patch("features.integrations.prompt_resolvers.simple_chat_error") as mock_error:
            mock_error.return_value = "Error response"
            result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.whatsapp_bot_sdk.set_reaction.assert_not_called()
        self.di.platform_bot_sdk.return_value.set_reaction.assert_not_called()
        mock_error.assert_called_once_with(str(error), emoji = "🧨")
        self.assertEqual(
            [call.args[1] for call in self.di.whatsapp_bot_sdk.send_text_message.call_args_list],
            ["First response", "Error response"],
        )
        self.assertEqual(
            events,
            ["rollback", "send:First response", "rollback", "send:Error response", "rollback", "sleep"],
        )
        self.assertEqual([call.args for call in self.mock_sleep.call_args_list], [(0.1,)])
        self.di.whatsapp_bot_sdk.mark_as_read.assert_not_called()
        self.di.chat_message_repo.save.assert_not_called()

    def test_general_exception_after_response_delivery_started_sends_error_without_reaction(self):
        resolved_domain_data_mock = self.__resolved_result(author = Mock(spec = User, id = UUID(int = 1)))
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [resolved_domain_data_mock]

        error = ServiceError(
            message = "Test error",
            error_code = PLATFORM_MAPPING_FAILED,
            http_status = 500,
            emoji = "🧨",
        )
        ErrorMsg = namedtuple("ErrorMsg", ["chat_id", "text"])
        response = [
            ErrorMsg(chat_id = "123", text = "First response"),
            ErrorMsg(chat_id = "123", text = "Second response"),
        ]
        error_response = [ErrorMsg(chat_id = "123", text = "Error response")]
        self.di.domain_langchain_mapper.map_bot_message_to_storage.side_effect = [response, error_response]
        events = []

        def send_text_message(chat, text):
            events.append(f"send:{text}")
            if text == "Second response":
                raise error

        def rollback_session():
            events.append("rollback")

        def sleep(delay):
            events.append("sleep")

        self.di.whatsapp_bot_sdk.send_text_message.side_effect = send_text_message
        self.di.rollback_db_session.side_effect = rollback_session
        self.mock_sleep.side_effect = sleep

        with patch("features.integrations.prompt_resolvers.simple_chat_error") as mock_error:
            mock_error.return_value = "Error response"
            result = respond_to_update(self.update)

        self.assertFalse(result)
        self.di.whatsapp_bot_sdk.set_reaction.assert_not_called()
        self.di.platform_bot_sdk.return_value.set_reaction.assert_not_called()
        mock_error.assert_called_once_with(str(error), emoji = "🧨")
        self.assertEqual(
            [call.args[1] for call in self.di.whatsapp_bot_sdk.send_text_message.call_args_list],
            ["First response", "Second response", "Error response"],
        )
        self.assertEqual([call.args for call in self.mock_sleep.call_args_list], [(0.1,), (0.1,)])
        self.assertEqual(
            events,
            [
                "rollback",
                "send:First response",
                "rollback",
                "sleep",
                "send:Second response",
                "rollback",
                "send:Error response",
                "rollback",
                "sleep",
            ],
        )
        self.di.chat_message_repo.save.assert_not_called()
