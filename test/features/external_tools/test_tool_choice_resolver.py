import unittest
from datetime import datetime
from unittest.mock import Mock
from uuid import UUID

from pydantic import SecretStr

from db.model.user import UserDB
from di.di import DI
from features.external_tools.access_token_resolver import AccessTokenResolver, ResolvedToken
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_6_SONNET,
    GPT_4O_MINI,
    TWELVE_DATA_STOCK_QUOTE,
)
from features.external_tools.tool_choice_resolver import ToolChoiceResolver, ToolResolutionError
from features.users.user import User


class ToolChoiceResolverTest(unittest.TestCase):

    invoker_user: User
    mock_access_token_resolver: Mock
    mock_di: DI

    def setUp(self):
        self.invoker_user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_user",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_openai_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_vision = "gpt-4o-mini",
            tool_choice_api_stock_quote = TWELVE_DATA_STOCK_QUOTE.id,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_access_token_resolver = Mock(spec = AccessTokenResolver)
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = self.invoker_user
        # noinspection PyPropertyAccess
        self.mock_di.access_token_resolver = self.mock_access_token_resolver

    def test_find_tool_by_id_success_existing_tool(self):
        tool = ToolChoiceResolver.find_tool_by_id(GPT_4O_MINI.id)
        self.assertEqual(tool, GPT_4O_MINI)

    def test_find_tool_by_id_success_anthropic_tool(self):
        tool = ToolChoiceResolver.find_tool_by_id(CLAUDE_4_6_SONNET.id)
        self.assertEqual(tool, CLAUDE_4_6_SONNET)

    def test_find_tool_by_id_failure_nonexistent_tool(self):
        tool = ToolChoiceResolver.find_tool_by_id("nonexistent-tool-id")
        self.assertIsNone(tool)

    def test_find_tool_by_id_failure_empty_string(self):
        tool = ToolChoiceResolver.find_tool_by_id("")
        self.assertIsNone(tool)

    def test_get_prioritized_tools_no_user_choice_no_default(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = None,
            default_tool = None,
        )

        self.assertGreater(len(tools), 1)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_prioritized_tools_only_user_choice(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = CLAUDE_4_6_SONNET,
            default_tool = None,
        )

        self.assertGreater(len(tools), 1)
        self.assertEqual(tools[0], CLAUDE_4_6_SONNET)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_prioritized_tools_only_default(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = None,
            default_tool = CLAUDE_4_6_SONNET,
        )

        self.assertGreater(len(tools), 1)
        self.assertEqual(tools[0], CLAUDE_4_6_SONNET)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_prioritized_tools_both_user_choice_and_default(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = CLAUDE_4_6_SONNET.id,
            default_tool = GPT_4O_MINI.id,
        )

        self.assertGreater(len(tools), 2)
        self.assertEqual(tools[0], CLAUDE_4_6_SONNET)
        self.assertEqual(tools[1], GPT_4O_MINI)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_prioritized_tools_user_choice_same_as_default_no_duplication(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = GPT_4O_MINI,
            default_tool = GPT_4O_MINI,
        )

        self.assertGreater(len(tools), 1)
        self.assertEqual(tools[0], GPT_4O_MINI)

        gpt_4o_mini_count = sum(1 for tool in tools if tool == GPT_4O_MINI)
        self.assertEqual(gpt_4o_mini_count, 1)

    def test_get_prioritized_tools_invalid_user_choice_tool_type(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.hearing,
            user_choice_tool = GPT_4O_MINI,
        )

        self.assertGreater(len(tools), 0)
        self.assertNotEqual(tools[0], GPT_4O_MINI)
        for tool in tools:
            self.assertIn(ToolType.hearing, tool.types)

    def test_get_prioritized_tools_nonexistent_tools_ignored(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = "nonexistent-user-tool",
            default_tool = "nonexistent-default-tool",
        )

        self.assertGreater(len(tools), 1)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_tool_success_user_has_access_to_user_choice(self):
        resolved = ResolvedToken(token = SecretStr("test_token"), payer_id = UUID(int = 1), uses_credits = False)
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsInstance(result, ConfiguredTool)
        self.assertEqual(result.definition, CLAUDE_4_6_SONNET)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)
        self.assertFalse(result.uses_credits)

    def test_get_tool_success_user_no_access_to_user_choice_but_has_access_to_others(self):
        resolved = ResolvedToken(token = SecretStr("test_token"), payer_id = UUID(int = 1), uses_credits = False)

        def mock_get_access_token_for_tool(test_tool):
            if test_tool == CLAUDE_4_6_SONNET:
                return None
            return resolved

        self.mock_access_token_resolver.get_access_token_for_tool.side_effect = mock_get_access_token_for_tool

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsInstance(result, ConfiguredTool)
        self.assertNotEqual(result.definition, CLAUDE_4_6_SONNET)
        self.assertIn(ToolType.chat, result.definition.types)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)

    def test_get_tool_success_with_default_tool_prioritized(self):
        resolved = ResolvedToken(token = SecretStr("test_token"), payer_id = UUID(int = 1), uses_credits = False)

        def mock_get_access_token_for_tool(test_tool):
            if test_tool == CLAUDE_4_6_SONNET:
                return None
            if test_tool == GPT_4O_MINI:
                return resolved
            return None

        self.mock_access_token_resolver.get_access_token_for_tool.side_effect = mock_get_access_token_for_tool

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat, default_tool = GPT_4O_MINI.id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsInstance(result, ConfiguredTool)
        self.assertEqual(result.definition, GPT_4O_MINI)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)

    def test_get_tool_failure_no_access_to_any_tool(self):
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = None

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat)

        self.assertIsNone(result)

    def test_require_tool_success(self):
        resolved = ResolvedToken(token = SecretStr("test_token"), payer_id = UUID(int = 1), uses_credits = False)
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.require_tool(ToolType.chat)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsInstance(result, ConfiguredTool)
        self.assertEqual(result.definition, CLAUDE_4_6_SONNET)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)

    def test_require_tool_failure_raises_exception(self):
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = None

        resolver = ToolChoiceResolver(self.mock_di)

        with self.assertRaises(ToolResolutionError) as context:
            resolver.require_tool(ToolType.chat)

        error_message = str(context.exception)
        self.assertIn("Unable to resolve a tool for 'chat'", error_message)
        self.assertIn(str(self.invoker_user.id.hex), error_message)

    def test_user_tool_choice_mapping_through_public_interface(self):
        resolved_1 = ResolvedToken(token = SecretStr("test_token_1"), payer_id = UUID(int = 1), uses_credits = False)
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved_1

        resolver = ToolChoiceResolver(self.mock_di)

        chat_result = resolver.get_tool(ToolType.chat)
        self.assertIsNotNone(chat_result)
        assert chat_result is not None
        self.assertIsInstance(chat_result, ConfiguredTool)
        self.assertEqual(chat_result.definition, CLAUDE_4_6_SONNET)
        self.assertEqual(chat_result.token.get_secret_value(), "test_token_1")
        self.assertEqual(chat_result.purpose, ToolType.chat)

        resolved_2 = ResolvedToken(token = SecretStr("test_token_2"), payer_id = UUID(int = 1), uses_credits = False)
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved_2

        vision_result = resolver.get_tool(ToolType.vision)
        self.assertIsNotNone(vision_result)
        assert vision_result is not None
        self.assertIsInstance(vision_result, ConfiguredTool)
        self.assertEqual(vision_result.definition, GPT_4O_MINI)
        self.assertEqual(vision_result.token.get_secret_value(), "test_token_2")
        self.assertEqual(vision_result.purpose, ToolType.vision)

        stock_result = resolver.get_tool(ToolType.api_stock_quote)
        self.assertIsNotNone(stock_result)
        assert stock_result is not None
        self.assertEqual(stock_result.definition, TWELVE_DATA_STOCK_QUOTE)
        self.assertEqual(stock_result.purpose, ToolType.api_stock_quote)
