import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.chat_message import ChatMessage
from db.schema.user import User, UserSave
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.chat_progress_notifier import ChatProgressNotifier
from features.chat.command_processor import CommandProcessor
from features.chat.config.chat_config import ChatConfig
from features.chat.llm_tools.llm_tool_library import LLMToolLibrary
from features.external_tools.tool_choice_resolver import ConfiguredTool
from features.integrations.integrations import resolve_agent_user
from util.error_codes import UNEXPECTED_ERROR, WAITLIST_ACCOUNT_NOT_ACTIVE, WAITLIST_INVITED_POLICIES_REQUIRED
from util.errors import AuthorizationError


class ChatAgentTest(unittest.TestCase):

    user: User
    agent_user: UserSave
    chat_config: ChatConfig
    mock_di: DI
    configured_tool: ConfiguredTool
    agent: ChatAgent

    def setUp(self):
        self.user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_user",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
            open_ai_key = SecretStr("test_openai_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        self.chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "12345",
            language_iso_code = "en",
            language_name = "English",
            title = "Test Chat",
            is_private = False,
            reply_chance_percent = 50,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

        # Create mock DI with all necessary dependencies
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = self.user
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = self.chat_config
        # noinspection PyPropertyAccess
        self.mock_di.require_invoker_chat = MagicMock(return_value = self.chat_config)
        # noinspection PyPropertyAccess
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        # noinspection PyPropertyAccess
        self.mock_di.command_processor = Mock(spec = CommandProcessor)
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = Mock()
        self.mock_di.authorization_service.require_user_is_chat_ready.return_value = self.user
        # noinspection PyPropertyAccess
        self.mock_di.llm_tool_library = Mock(spec = LLMToolLibrary)
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service = Mock()
        mock_membership = Mock()
        mock_membership.max_chat_history_depth = 30
        mock_membership.max_output_tokens = 500
        mock_membership.max_iterations = 20
        self.mock_di.chat_membership_service.get.return_value = mock_membership
        # noinspection PyPropertyAccess
        self.mock_di.chat_progress_notifier = Mock(return_value = Mock(spec = ChatProgressNotifier))
        # noinspection PyPropertyAccess
        self.mock_di.chat_langchain_model = Mock(return_value = Mock(spec = BaseChatModel))

        # Setup method return values
        self.mock_di.llm_tool_library.bind_tools.return_value = Mock(spec = Runnable)
        # noinspection PyPropertyAccess
        self.mock_di.llm_tool_library.tool_names = ["test_tool"]

        # noinspection PyTypeChecker
        self.configured_tool = Mock()

        # Mock message/attachment fetching used in ChatAgent.__init__
        mock_latest_message = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "Test message",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [mock_latest_message]
        self.mock_di.chat_message_attachment_repo.get_all_by_message.return_value = []
        self.mock_di.user_crud.get.return_value = None
        self.mock_di.domain_langchain_mapper.map_to_langchain.return_value = HumanMessage("Test message")

        self.sleep_patcher = patch("features.chat.chat_agent.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()

        self.agent = ChatAgent(
            raw_last_message = "Test message",
            last_message_id = "msg_123",
            configured_tool = self.configured_tool,
            di = self.mock_di,
        )
        # reset so per-test assertions don't count the init call
        self.mock_di.chat_message_crud.get_latest_chat_messages.reset_mock()

    def test_init_fetches_invoker_membership(self):
        self.mock_di.chat_membership_service.get.assert_called_once_with(
            self.user.id,
            self.chat_config.chat_id,
        )

    def test_init_fetches_message_attachments_from_repository(self):
        self.mock_di.chat_message_attachment_repo.get_all_by_message.assert_called_once_with(
            self.chat_config.chat_id,
            "msg_123",
        )

    def test_process_commands_no_api_key(self):
        # Create bot without configured_tool
        bot_no_key = ChatAgent(
            raw_last_message = "Test message",
            last_message_id = "msg_123",
            configured_tool = None,
            di = self.mock_di,
        )

        self.mock_di.command_processor.execute.return_value = CommandProcessor.Result(
            "ignored",
            None,
            None,
        )
        result = bot_no_key.process_commands()
        self.assertFalse(result.is_handled)
        self.assertIsNone(result.reply)

    def test_process_commands_failed(self):
        self.mock_di.command_processor.execute.return_value = CommandProcessor.Result(
            "failed",
            "Failed to process command.",
            UNEXPECTED_ERROR,
        )
        result = self.agent.process_commands()
        self.assertTrue(result.is_handled)
        self.assertIsNotNone(result.reply)
        self.assertIn("Failed to process command.", result.reply.content)

    def test_process_commands_success(self):
        self.mock_di.command_processor.execute.return_value = CommandProcessor.Result(
            "success",
            None,
            None,
        )
        result = self.agent.process_commands()
        self.assertTrue(result.is_handled)
        self.assertIsNone(result.reply)

    def test_should_reply_private_chat(self):
        self.chat_config.is_private = True
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "Hello"

        self.assertTrue(self.agent.should_reply())

    def test_should_reply_bot_mentioned(self):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = f"Hello @{self.agent_user.telegram_username}"

        self.assertTrue(self.agent.should_reply())

    @patch("random.randint")
    def test_should_reply_random_chance(self, mock_randint):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 50
        self.agent._ChatAgent__raw_last_message = "Hello"

        mock_randint.return_value = 25
        self.assertTrue(self.agent.should_reply())

        mock_randint.return_value = 75
        self.assertFalse(self.agent.should_reply())

    def test_is_dispatchable_rejects_empty_message(self):
        self.chat_config.is_private = True
        self.chat_config.reply_chance_percent = 100
        self.agent._ChatAgent__raw_last_message = " "

        self.assertFalse(self.agent._ChatAgent__is_dispatchable())

    def test_should_not_reply_zero_chance(self):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "Hello"

        self.assertFalse(self.agent.should_reply())

    def test_should_not_reply_100_chance(self):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 100
        self.agent._ChatAgent__raw_last_message = "Hello"

        self.assertTrue(self.agent.should_reply())

    def test_should_reply_group_chat(self):
        self.chat_config.is_private = False
        self.chat_config.title = "Group Chat"
        self.chat_config.reply_chance_percent = 100
        self.agent._ChatAgent__raw_last_message = "Hello"

        self.assertTrue(self.agent.should_reply())

    # noinspection PyUnresolvedReferences
    def test_is_dispatchable_rejects_self_authored(self):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 100
        self.agent._ChatAgent__raw_last_message = "Hello"
        self.mock_di.invoker.telegram_username = self.agent_user.telegram_username

        self.assertFalse(self.agent._ChatAgent__is_dispatchable())

    # noinspection PyUnresolvedReferences
    def test_is_dispatchable_accepts_other_user(self):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 100
        self.agent._ChatAgent__raw_last_message = "Hello"
        self.mock_di.invoker.telegram_username = "other_user"

        self.assertTrue(self.agent._ChatAgent__is_dispatchable())

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_no_reply_needed(self, mock_should_reply):
        mock_should_reply.return_value = False
        result = self.agent.execute()
        self.assertIsNone(result)

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_command_processed(self, mock_should_reply, mock_process_commands):
        self.chat_config.is_private = True
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = True,
            reply = None,
        )
        result = self.agent.execute()
        self.assertIsNone(result)

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_command_failed(self, mock_should_reply, mock_process_commands):
        self.chat_config.is_private = True
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = True,
            reply = AIMessage("Failed to process command."),
        )
        result = self.agent.execute()
        self.assertIn("Failed to process command.", result.content)

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_no_api_key(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )

        # Create a new bot instance without configured_tool (simulating no API key)
        bot_no_key = ChatAgent(
            raw_last_message = "Test message",
            last_message_id = "msg_123",
            configured_tool = None,
            di = self.mock_di,
        )

        result = bot_no_key.execute()
        self.assertIn("Not configured", result.content)

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_llm_response(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )

        # Mock the tools_model invoke to return the final response
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("LLM response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()
        self.assertEqual(result.content, "LLM response")

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_tool_call(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )
        tool_call = {"id": "1", "name": "test_tool", "args": {}}

        # Create AI messages with tool_calls attribute
        ai_with_tools = AIMessage(content = "", tool_calls = [tool_call])
        ai_final = AIMessage("Final response")

        # Mock the tools_model to return first tool calls, then final response
        mock_tools_model = Mock()
        mock_tools_model.invoke.side_effect = [ai_with_tools, ai_final]
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model
        self.mock_di.llm_tool_library.invoke.return_value = "Tool result"

        result = self.agent.execute()
        self.assertEqual(result.content, "Final response")

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_exception(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )

        # Mock the tools_model to raise an exception
        mock_tools_model = Mock()
        mock_tools_model.invoke.side_effect = Exception("Test error")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()
        self.assertIn("🤯", result.content)
        self.assertIn("Test error", result.content)
        self.assertIn("/settings", result.content)

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_max_iterations_exceeded(self, mock_should_reply, mock_process_commands, mock_config):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )
        mock_config.chat_debounce_delay_s = 0.0
        self.agent._ChatAgent__max_iterations = 2

        # Create AI messages with tool_calls to simulate continued iterations
        tool_call = {"id": "1", "name": "test_tool", "args": {}}
        ai_with_tools = AIMessage(content = "", tool_calls = [tool_call])

        # Make the LLM always return messages with tool calls to continue iterations
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = ai_with_tools
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model
        self.mock_di.llm_tool_library.invoke.return_value = "Tool result"

        result = self.agent.execute()

        # The OverflowError should be caught and converted to an AIMessage with error content
        self.assertIsInstance(result, AIMessage)
        self.assertIn("⚠️", result.content)  # InternalError emoji
        self.assertIn("Reached max iterations", result.content)
        self.assertIn("2", result.content)  # Should include the max iterations count

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_waitlist_guard_blocks_unknown_commands(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Waitlisted account is not active yet",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertIsNotNone(result)
        self.assertIn("waitlist", result.content.lower())

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_waitlist_guard_does_not_override_command_failure(self, mock_should_reply, mock_process_commands):
        self.chat_config.is_private = True
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = True,
            reply = AIMessage("Failed to process command."),
        )
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Waitlisted account is not active yet",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertIsNotNone(result)
        self.assertIn("Failed to process command.", result.content)

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_policy_guard_blocks_active_user_without_policy(self, mock_should_reply, mock_process_commands):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(
            is_handled = False,
            reply = None,
        )
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Accept policies in /settings first.",
            WAITLIST_INVITED_POLICIES_REQUIRED,
        )

        result = self.agent.execute()
        self.assertIsNotNone(result)
        self.assertIn("policies", result.content.lower())

    def tearDown(self):
        self.sleep_patcher.stop()

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_has_newer_burst_message_disabled_when_delay_is_zero(self, mock_should_reply, mock_process_commands, mock_config):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 0.0
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        self.agent.execute()

        self.mock_sleep.assert_not_called()
        self.mock_di.chat_message_crud.get_latest_chat_messages.assert_not_called()

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_has_newer_burst_message_proceeds_when_message_is_latest(
        self, mock_should_reply, mock_process_commands, mock_config,
    ):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("LLM response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.mock_sleep.assert_called_once_with(1.0)
        self.assertEqual(result.content, "LLM response")

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_has_newer_burst_message_skips_llm_when_newer_message_exists(
        self, mock_should_reply, mock_process_commands, mock_config,
    ):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0
        newer_message = Mock()
        newer_message.message_id = "msg_999"
        newer_message.author_id = self.user.id
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [newer_message]

        result = self.agent.execute()

        self.mock_sleep.assert_called_once_with(1.0)
        self.assertIsNone(result)
        self.mock_di.llm_tool_library.bind_tools.assert_not_called()

    def test_is_addressable_private_chat(self):
        self.chat_config.is_private = True
        self.agent._ChatAgent__raw_last_message = "anything"

        self.assertTrue(self.agent._ChatAgent__is_addressable())

    def test_is_addressable_group_chat_with_mention(self):
        self.chat_config.is_private = False
        self.agent._ChatAgent__raw_last_message = f"hello @{self.agent_user.telegram_username}"

        self.assertTrue(self.agent._ChatAgent__is_addressable())

    def test_is_addressable_group_chat_without_mention(self):
        self.chat_config.is_private = False
        self.agent._ChatAgent__raw_last_message = "hello"

        self.assertFalse(self.agent._ChatAgent__is_addressable())

    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_skips_commands_when_not_addressable(self, mock_should_reply, mock_process_commands):
        self.chat_config.is_private = False
        self.agent._ChatAgent__raw_last_message = "hello"
        mock_should_reply.return_value = False

        result = self.agent.execute()

        self.assertIsNone(result)
        mock_process_commands.assert_not_called()

    @patch("features.chat.chat_agent.config")
    def test_should_reply_carries_mention_from_recent_burst_message(self, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        recent_tagged = ChatMessage(
            message_id = "msg_001",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = f"Hello @{self.agent_user.telegram_username}",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "follow up",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [current, recent_tagged]

        self.assertTrue(self.agent.should_reply())

    @patch("features.chat.chat_agent.config")
    def test_should_reply_ignores_mention_from_different_invoker(self, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        other_tagged = ChatMessage(
            message_id = "msg_001",
            author_id = UUID(int = 999),
            sent_at = datetime.now(),
            text = f"Hello @{self.agent_user.telegram_username}",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "follow up",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [current, other_tagged]

        self.assertFalse(self.agent.should_reply())

    @patch("features.chat.chat_agent.config")
    def test_should_reply_ignores_mention_after_bot_response(self, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        bot_reply = ChatMessage(
            message_id = "msg_002",
            author_id = self.agent_user.id,
            sent_at = datetime.now(),
            text = "you're welcome",
            chat_id = self.chat_config.chat_id,
        )
        old_tagged = ChatMessage(
            message_id = "msg_001",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = f"Hello @{self.agent_user.telegram_username}",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "follow up",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [current, bot_reply, old_tagged]

        self.assertFalse(self.agent.should_reply())

    @patch("features.chat.chat_agent.config")
    def test_should_reply_skips_chain_walk_when_debounce_disabled(self, mock_config):
        # debounce=0 turns off burst coordination, so carry-over must not run — otherwise
        # an untagged follow-up could double-respond alongside the still-running tagged
        # message's instance (no chain-break in DB yet).
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up with no tag"
        mock_config.chat_debounce_delay_s = 0.0
        mock_config.chat_history_depth = 30
        recent_tagged = Mock()
        recent_tagged.message_id = "msg_001"
        recent_tagged.author_id = self.user.id
        recent_tagged.sent_at = datetime.now()
        recent_tagged.text = f"Hello @{self.agent_user.telegram_username}"
        current = Mock()
        current.message_id = "msg_123"
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [current, recent_tagged]

        self.assertFalse(self.agent.should_reply())
        # the chain walk must not even hit the DB when debounce is disabled
        self.mock_di.chat_message_crud.get_latest_chat_messages.assert_not_called()

    @patch("features.chat.chat_agent.config")
    def test_should_reply_direct_mention_works_when_debounce_disabled(self, mock_config):
        # direct mention in the current message must always trigger a reply, even with
        # the chain walk disabled by debounce=0
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = f"hey @{self.agent_user.telegram_username}"
        mock_config.chat_debounce_delay_s = 0.0
        mock_config.chat_history_depth = 30

        self.assertTrue(self.agent.should_reply())
        self.mock_di.chat_message_crud.get_latest_chat_messages.assert_not_called()

    @patch("features.chat.chat_agent.config")
    def test_should_reply_skips_command_message_in_burst(self, mock_config):
        # Command messages tag the bot as part of syntax, not as a conversational mention.
        # The chain walk must skip them so a follow-up does not inherit the command's tag,
        # even when the command's bot reply is racing to land in the DB.
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "hey guys what's up"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        command_message = ChatMessage(
            message_id = "msg_001",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = f"/help@{self.agent_user.telegram_username}",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "hey guys what's up",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [current, command_message]

        self.assertFalse(self.agent.should_reply())

    @patch("features.chat.chat_agent.config")
    def test_should_reply_carries_mention_from_seconds_old_burst_message(self, mock_config):
        # Regression for prod bug: bot did not reply to msg3 (no tag) when msg2 (TAG)
        # arrived within seconds. The should_reply call always happens after a debounce
        # sleep, so any prior burst message is older than debounce_delay_s by definition
        # — a cutoff of now - debounce_delay_s excludes exactly the messages we want to
        # carry the mention from.
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up with no tag"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        tagged_older = ChatMessage(
            message_id = "msg_002",
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(seconds = 5),
            text = f"@{self.agent_user.telegram_username} this message should trigger a response",
            chat_id = self.chat_config.chat_id,
        )
        earlier_untagged = ChatMessage(
            message_id = "msg_001",
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(seconds = 60),
            text = "I think I fixed it",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "follow up with no tag",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [
            current, tagged_older, earlier_untagged,
        ]

        self.assertTrue(self.agent.should_reply())

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_has_newer_burst_message_ignores_newer_message_from_different_author(
        self, mock_should_reply, mock_process_commands, mock_config,
    ):
        mock_should_reply.return_value = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0

        newer_message_other_user = Mock()
        newer_message_other_user.message_id = "msg_999"
        newer_message_other_user.author_id = UUID(int = 999)
        our_message = Mock()
        our_message.message_id = "msg_123"
        our_message.author_id = self.user.id
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [
            newer_message_other_user, our_message,
        ]
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("LLM response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "LLM response")

    @patch("features.chat.chat_agent.config")
    def test_should_reply_carries_mention_past_other_user_messages(self, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = "follow up with no tag"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        other_user_msg = ChatMessage(
            message_id = "msg_003",
            author_id = UUID(int = 888),
            sent_at = datetime.now(),
            text = "some unrelated message",
            chat_id = self.chat_config.chat_id,
        )
        tagged_by_invoker = ChatMessage(
            message_id = "msg_002",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = f"@{self.agent_user.telegram_username} help me",
            chat_id = self.chat_config.chat_id,
        )
        current = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "follow up with no tag",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [
            current, other_user_msg, tagged_by_invoker,
        ]

        self.assertTrue(self.agent.should_reply())

    # --- GROUP 1a: burst from same user, all tagged ---

    @patch("features.chat.chat_agent.config")
    def test_group_burst_same_user_all_tagged_carries_mention(self, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        self.agent._ChatAgent__raw_last_message = f"@{self.agent_user.telegram_username} second thought"
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30

        self.assertTrue(self.agent.should_reply())

    # --- GROUP 1c: burst from same user, first untagged then tagged ---

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    def test_group_burst_same_user_tagged_winner_replies(self, mock_process_commands, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0

        mock_config.chat_history_depth = 30
        self.agent._ChatAgent__raw_last_message = f"@{self.agent_user.telegram_username} actually this"
        our_message = Mock()
        our_message.message_id = "msg_123"
        our_message.author_id = self.user.id
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [our_message]
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "response")

    # --- GROUP 2c: burst from different users, first untagged then tagged ---

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    def test_group_burst_different_users_tagged_user_not_suppressed(self, mock_process_commands, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0

        mock_config.chat_history_depth = 30
        self.agent._ChatAgent__raw_last_message = f"@{self.agent_user.telegram_username} hey bot"
        newer_from_other = Mock()
        newer_from_other.message_id = "msg_200"
        newer_from_other.author_id = UUID(int = 888)
        our_tagged = Mock()
        our_tagged.message_id = "msg_123"
        our_tagged.author_id = self.user.id
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [
            newer_from_other, our_tagged,
        ]
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("bot reply")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "bot reply")

    # --- GROUP 2d: burst from different users, no tags ---

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    def test_group_burst_different_users_no_tags_no_reply(self, mock_process_commands, mock_config):
        self.chat_config.is_private = False
        self.chat_config.reply_chance_percent = 0
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0
        mock_config.chat_history_depth = 30
        self.agent._ChatAgent__raw_last_message = "just chatting"
        newer_from_other = ChatMessage(
            message_id = "msg_200",
            author_id = UUID(int = 888),
            sent_at = datetime.now(),
            text = "hey everyone",
            chat_id = self.chat_config.chat_id,
        )
        our_message = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "just chatting",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [
            newer_from_other, our_message,
        ]

        result = self.agent.execute()

        self.assertIsNone(result)

    # --- SINGLE 1: burst in private chat ---

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    def test_private_burst_winner_always_replies(self, mock_process_commands, mock_config):
        self.chat_config.is_private = True
        self.chat_config.reply_chance_percent = 0
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0

        mock_config.chat_history_depth = 30
        self.agent._ChatAgent__raw_last_message = "last message in burst"
        our_message = ChatMessage(
            message_id = "msg_123",
            author_id = self.user.id,
            sent_at = datetime.now(),
            text = "last message in burst",
            chat_id = self.chat_config.chat_id,
        )
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [our_message]
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("private reply")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "private reply")

    @patch("features.chat.chat_agent.config")
    @patch("features.chat.chat_agent.ChatAgent.process_commands")
    def test_private_burst_older_message_suppressed(self, mock_process_commands, mock_config):
        self.chat_config.is_private = True
        mock_process_commands.return_value = ChatAgent.CommandHandlingResult(is_handled = False, reply = None)
        mock_config.chat_debounce_delay_s = 1.0
        self.agent._ChatAgent__raw_last_message = "first message"
        newer_message = Mock()
        newer_message.message_id = "msg_999"
        newer_message.author_id = self.user.id
        self.mock_di.chat_message_crud.get_latest_chat_messages.return_value = [newer_message]

        result = self.agent.execute()

        self.assertIsNone(result)
