import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import stubs
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.chat_progress_notifier import ChatProgressNotifier
from features.chat.command_processor import CommandProcessor
from features.chat.llm_tools.llm_tool_library import LLMToolLibrary
from features.integrations.integrations import resolve_agent_user
from features.users.user import User
from util.error_codes import UNEXPECTED_ERROR, WAITLIST_ACCOUNT_NOT_ACTIVE, WAITLIST_INVITED_POLICIES_REQUIRED
from util.errors import AuthorizationError


class ChatAgentTest(unittest.TestCase):

    agent_user: User
    mock_di: DI
    agent: ChatAgent

    def setUp(self):
        user = stubs.domain.user(
            telegram_chat_id = "test_chat_id",
            is_invited_to_start = False,
        )
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        chat_config = stubs.domain.chat_config(
            is_private = False,
            reply_chance_percent = 50,
        )

        # Create mock DI with all necessary dependencies
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = chat_config
        # noinspection PyPropertyAccess
        self.mock_di.require_invoker_chat = MagicMock(return_value = chat_config)
        # noinspection PyPropertyAccess
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        # noinspection PyPropertyAccess
        self.mock_di.command_processor = Mock(spec = CommandProcessor)
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = Mock()
        self.mock_di.authorization_service.require_user_is_chat_ready.return_value = user
        # noinspection PyPropertyAccess
        self.mock_di.llm_tool_library = Mock(spec = LLMToolLibrary)
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service = Mock()
        membership = stubs.domain.chat_membership(
            user_id = user.id,
            chat_id = chat_config.chat_id,
            max_output_tokens = 500,
        )
        self.mock_di.chat_membership_service.get.return_value = membership
        # noinspection PyPropertyAccess
        self.mock_di.chat_progress_notifier = Mock(return_value = Mock(spec = ChatProgressNotifier))
        # noinspection PyPropertyAccess
        self.mock_di.chat_langchain_model = Mock(return_value = Mock(spec = BaseChatModel))

        # setup platform SDK and settings controller for error routing
        self.mock_platform_sdk = Mock()
        self.mock_di.platform_bot_sdk = Mock(return_value = self.mock_platform_sdk)
        settings_link = stubs.api.settings_link_response()
        self.mock_di.settings_controller = Mock()
        self.mock_di.settings_controller.create_settings_link = Mock(return_value = settings_link)

        # setup method return values
        self.mock_di.llm_tool_library.bind_tools.return_value = Mock(spec = Runnable)
        # noinspection PyPropertyAccess
        self.mock_di.llm_tool_library.tool_names = ["test_tool"]

        configured_tool = stubs.domain.configured_tool()

        # configure message and attachment fetching used in ChatAgent.__init__
        self.cutoff_sent_at = datetime.now()
        latest_message = stubs.domain.chat_message(
            message_id = "msg_123",
            sent_at = self.cutoff_sent_at,
            text = "Test message",
        )
        self.mock_di.chat_message_repo.get_latest_by_chat.return_value = [latest_message]
        self.mock_di.chat_attachment_repo.get_all_by_message.return_value = []
        self.mock_di.user_repo.get.return_value = None
        self.mock_di.domain_langchain_mapper.map_to_langchain.return_value = HumanMessage("Test message")

        self.agent = ChatAgent(
            trigger_message_text = "Test message",
            trigger_message_id = "msg_123",
            configured_tool = configured_tool,
            di = self.mock_di,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
            explicitly_addressed = False,
        )
        # reset so per-test assertions don't count the init call
        self.mock_di.chat_message_repo.get_latest_by_chat.reset_mock()

    def test_init_fetches_invoker_membership(self):
        self.mock_di.chat_membership_service.get.assert_called_once_with(
            self.mock_di.invoker.id,
            self.mock_di.invoker_chat.chat_id,
        )

    def test_init_does_not_fetch_chat_attachments_from_repository(self):
        self.mock_di.chat_attachment_repo.get_all_by_message.assert_not_called()

    def test_process_commands_no_api_key(self):
        # Create bot without configured_tool
        bot_no_key = ChatAgent(
            trigger_message_text = "Test message",
            trigger_message_id = "msg_123",
            configured_tool = None,
            di = self.mock_di,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
            explicitly_addressed = False,
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
        self.assertEqual(result.reply.content, "🤯")
        self.mock_platform_sdk.send_text_message.assert_called_once()
        self.mock_platform_sdk.send_button_link.assert_called_once()

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
        self.mock_di.invoker_chat.is_private = True
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__trigger_message_text = "Hello"

        self.assertTrue(self.agent.should_reply())

    def test_should_reply_explicitly_addressed(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__explicitly_addressed = True

        self.assertTrue(self.agent.should_reply())

    def test_should_not_reply_when_bot_mention_is_only_quoted(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0

        for quote_prefix in [">>", ">>>>"]:
            with self.subTest(quote_prefix = quote_prefix):
                self.agent._ChatAgent__trigger_message_text = (
                    f"{quote_prefix} Hello @{self.agent_user.telegram_username}\n\nI agree"
                )

                self.assertFalse(self.agent.should_reply())

    def test_should_reply_with_aggregated_addressing_after_quote(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__explicitly_addressed = True

        self.assertTrue(self.agent.should_reply())

    @patch("random.randint")
    def test_should_reply_random_chance(self, mock_randint):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 50
        self.agent._ChatAgent__trigger_message_text = "Hello"

        mock_randint.return_value = 25
        self.assertTrue(self.agent.should_reply())

        mock_randint.return_value = 75
        self.assertFalse(self.agent.should_reply())

    def test_is_dispatchable_rejects_empty_message(self):
        self.mock_di.invoker_chat.is_private = True
        self.mock_di.invoker_chat.reply_chance_percent = 100
        self.agent._ChatAgent__trigger_message_text = " "

        self.assertFalse(self.agent._ChatAgent__is_dispatchable())

    def test_should_not_reply_zero_chance(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__trigger_message_text = "Hello"

        self.assertFalse(self.agent.should_reply())

    def test_should_not_reply_100_chance(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 100
        self.agent._ChatAgent__trigger_message_text = "Hello"

        self.assertTrue(self.agent.should_reply())

    def test_should_reply_group_chat(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.title = "Group Chat"
        self.mock_di.invoker_chat.reply_chance_percent = 100
        self.agent._ChatAgent__trigger_message_text = "Hello"

        self.assertTrue(self.agent.should_reply())

    # noinspection PyUnresolvedReferences
    def test_is_dispatchable_rejects_self_authored(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 100
        self.agent._ChatAgent__trigger_message_text = "Hello"
        self.mock_di.invoker.telegram_username = self.agent_user.telegram_username

        self.assertFalse(self.agent._ChatAgent__is_dispatchable())

    # noinspection PyUnresolvedReferences
    def test_is_dispatchable_accepts_other_user(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 100
        self.agent._ChatAgent__trigger_message_text = "Hello"
        self.mock_di.invoker.telegram_username = "other_user"

        self.assertTrue(self.agent._ChatAgent__is_dispatchable())

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_no_reply_needed(self, mock_should_reply):
        mock_should_reply.return_value = False
        result = self.agent.execute()
        self.assertIsNone(result)

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_no_api_key(self, mock_should_reply):
        mock_should_reply.return_value = True

        # Create a new bot instance without configured_tool (simulating no API key)
        bot_no_key = ChatAgent(
            trigger_message_text = "Test message",
            trigger_message_id = "msg_123",
            configured_tool = None,
            di = self.mock_di,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
            explicitly_addressed = False,
        )

        result = bot_no_key.execute()
        self.assertEqual(result.content, "🤯")
        self.mock_platform_sdk.send_text_message.assert_called_once()
        self.assertIn("Not configured", self.mock_platform_sdk.send_text_message.call_args[0][1])

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_llm_response(self, mock_should_reply):
        mock_should_reply.return_value = True

        # Mock the tools_model invoke to return the final response
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("LLM response")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()
        self.assertEqual(result.content, "LLM response")

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_removes_attachment_placeholder_from_llm_response(self, mock_should_reply):
        mock_should_reply.return_value = True
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("Here you go\n\n📎 [ a1 (image/png) ]\n\nDone")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "Here you go\n\nDone")

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_removes_attachment_placeholder_only_llm_response(self, mock_should_reply):
        mock_should_reply.return_value = True
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage("📎 [ a1 (image/png) ]")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, "")

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_removes_attachment_placeholder_from_llm_content_blocks(
        self,
        mock_should_reply,
    ):
        mock_should_reply.return_value = True
        mock_tools_model = Mock()
        mock_tools_model.invoke.return_value = AIMessage(content = [
            {"type": "text", "text": "Here\n📎 [ a1 (image/png) ]"},
            "📎 [ a2 ]",
            {"type": "thinking", "thinking": "internal"},
        ])
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()

        self.assertEqual(result.content, [
            {"type": "text", "text": "Here"},
            {"type": "thinking", "thinking": "internal"},
        ])

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_tool_call(self, mock_should_reply):
        mock_should_reply.return_value = True
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

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_exception(self, mock_should_reply):
        mock_should_reply.return_value = True

        # Mock the tools_model to raise an exception
        mock_tools_model = Mock()
        mock_tools_model.invoke.side_effect = Exception("Test error")
        self.mock_di.llm_tool_library.bind_tools.return_value = mock_tools_model

        result = self.agent.execute()
        self.assertEqual(result.content, "🤯")
        self.mock_platform_sdk.send_text_message.assert_called_once()
        self.assertIn("Test error", self.mock_platform_sdk.send_text_message.call_args[0][1])
        self.mock_platform_sdk.send_button_link.assert_called_once()

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_max_iterations_exceeded(self, mock_should_reply):
        mock_should_reply.return_value = True
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

        # error is routed to private chat, originating chat gets emoji only
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "⚠️")
        self.mock_platform_sdk.send_text_message.assert_called_once()
        sent_text = self.mock_platform_sdk.send_text_message.call_args[0][1]
        self.assertIn("Reached max iterations", sent_text)
        self.assertIn("2", sent_text)

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_waitlist_guard_blocks_unknown_commands(self, mock_should_reply):
        mock_should_reply.return_value = True
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Waitlisted account is not active yet",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertIsNotNone(result)
        self.assertEqual(result.content, "🔒")
        self.assertIn("waitlist", self.mock_platform_sdk.send_text_message.call_args[0][1].lower())

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_execute_policy_guard_blocks_active_user_without_policy(self, mock_should_reply):
        mock_should_reply.return_value = True
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Accept policies in /settings first.",
            WAITLIST_INVITED_POLICIES_REQUIRED,
        )

        result = self.agent.execute()
        self.assertIsNotNone(result)
        self.assertEqual(result.content, "🔒")
        self.assertIn("policies", self.mock_platform_sdk.send_text_message.call_args[0][1].lower())

    def test_init_bounds_history_to_claimed_cutoff(self):
        self.mock_di.chat_message_repo.get_latest_by_chat.reset_mock()
        configured_tool = stubs.domain.configured_tool()

        ChatAgent(
            trigger_message_text = "Test message",
            trigger_message_id = "msg_123",
            configured_tool = configured_tool,
            di = self.mock_di,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
            explicitly_addressed = True,
        )

        self.mock_di.chat_message_repo.get_latest_by_chat.assert_called_once_with(
            chat_id = self.mock_di.invoker_chat.chat_id,
            limit = 30,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
        )

    def test_should_reply_to_explicitly_addressed_group_burst(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__explicitly_addressed = True

        self.assertTrue(self.agent.should_reply())

    def test_should_not_reply_to_unaddressed_zero_chance_group_burst(self):
        self.mock_di.invoker_chat.is_private = False
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__explicitly_addressed = False

        self.assertFalse(self.agent.should_reply())

    def test_should_reply_to_private_burst_without_explicit_address(self):
        self.mock_di.invoker_chat.is_private = True
        self.mock_di.invoker_chat.reply_chance_percent = 0
        self.agent._ChatAgent__explicitly_addressed = False

        self.assertTrue(self.agent.should_reply())

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_error_routes_to_private_chat_with_settings_link(self, mock_should_reply):
        mock_should_reply.return_value = True
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Some auth error",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertEqual(result.content, "🔒")
        sent_text = self.mock_platform_sdk.send_text_message.call_args[0][1]
        sent_chat = self.mock_platform_sdk.send_text_message.call_args[0][0]
        self.assertEqual(sent_chat, "test_chat_id")
        self.assertIn("🔒", sent_text)
        self.assertIn("Some auth error", sent_text)
        self.mock_platform_sdk.send_button_link.assert_called_once_with(
            "test_chat_id",
            "https://example.com/settings",
        )

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_error_falls_back_to_inline_when_no_private_chat(self, mock_should_reply):
        mock_should_reply.return_value = True
        self.mock_di.invoker.telegram_chat_id = None
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Some auth error",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertIn("Some auth error", result.content)
        self.assertIn("Check settings", result.content)
        self.mock_platform_sdk.send_text_message.assert_not_called()
        self.mock_platform_sdk.send_button_link.assert_not_called()

    @patch("features.chat.chat_agent.ChatAgent.should_reply")
    def test_error_routing_swallows_private_chat_delivery_failure(self, mock_should_reply):
        mock_should_reply.return_value = True
        self.mock_platform_sdk.send_text_message.side_effect = Exception("Network error")
        self.mock_di.authorization_service.require_user_is_chat_ready.side_effect = AuthorizationError(
            "Some auth error",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )

        result = self.agent.execute()
        self.assertIn("Some auth error", result.content)
        self.assertIn("Check settings", result.content)
        self.mock_platform_sdk.send_button_link.assert_not_called()
