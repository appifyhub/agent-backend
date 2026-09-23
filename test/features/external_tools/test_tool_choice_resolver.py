import unittest
from unittest.mock import Mock

import stubs
from pydantic import SecretStr

from di.di import DI
from features.external_tools.access_token_resolver import AccessTokenResolver
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_6_SONNET,
    GPT_5_6_TERRA,
    TWELVE_DATA_STOCK_QUOTE,
    VIDEO_GEN_P_VIDEO,
)
from features.external_tools.tool_choice_resolver import ToolChoiceResolver, ToolResolutionError


class ToolChoiceResolverTest(unittest.TestCase):

    mock_access_token_resolver: Mock
    mock_di: DI

    def setUp(self):
        self.mock_access_token_resolver = Mock(spec = AccessTokenResolver)
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.access_token_resolver = self.mock_access_token_resolver

    def test_find_tool_by_id_success_existing_tool(self):
        tool = ToolChoiceResolver.find_tool_by_id(GPT_5_6_TERRA.id)
        self.assertEqual(tool, GPT_5_6_TERRA)

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
            default_tool = GPT_5_6_TERRA.id,
        )

        self.assertGreater(len(tools), 2)
        self.assertEqual(tools[0], CLAUDE_4_6_SONNET)
        self.assertEqual(tools[1], GPT_5_6_TERRA)
        for tool in tools:
            self.assertIn(ToolType.chat, tool.types)

    def test_get_prioritized_tools_user_choice_same_as_default_no_duplication(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.chat,
            user_choice_tool = GPT_5_6_TERRA,
            default_tool = GPT_5_6_TERRA,
        )

        self.assertGreater(len(tools), 1)
        self.assertEqual(tools[0], GPT_5_6_TERRA)

        gpt_5_6_terra_count = sum(1 for tool in tools if tool == GPT_5_6_TERRA)
        self.assertEqual(gpt_5_6_terra_count, 1)

    def test_get_prioritized_tools_invalid_user_choice_tool_type(self):
        tools = ToolChoiceResolver.get_prioritized_tools(
            ToolType.hearing,
            user_choice_tool = GPT_5_6_TERRA,
        )

        self.assertGreater(len(tools), 0)
        self.assertNotEqual(tools[0], GPT_5_6_TERRA)
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
        resolved = stubs.domain.resolved_token(token = SecretStr("test_token"))
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

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
        resolved = stubs.domain.resolved_token(token = SecretStr("test_token"))

        def mock_get_access_token_for_tool(test_tool):
            if test_tool == CLAUDE_4_6_SONNET:
                return None
            return resolved

        self.mock_access_token_resolver.get_access_token_for_tool.side_effect = mock_get_access_token_for_tool
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

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
        resolved = stubs.domain.resolved_token(token = SecretStr("test_token"))

        def mock_get_access_token_for_tool(test_tool):
            if test_tool == CLAUDE_4_6_SONNET:
                return None
            if test_tool == GPT_5_6_TERRA:
                return resolved
            return None

        self.mock_access_token_resolver.get_access_token_for_tool.side_effect = mock_get_access_token_for_tool
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat, default_tool = GPT_5_6_TERRA.id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsInstance(result, ConfiguredTool)
        self.assertEqual(result.definition, GPT_5_6_TERRA)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)

    def test_get_tool_failure_no_access_to_any_tool(self):
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = None
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

        resolver = ToolChoiceResolver(self.mock_di)
        result = resolver.get_tool(ToolType.chat)

        self.assertIsNone(result)

    def test_require_tool_success(self):
        resolved = stubs.domain.resolved_token(token = SecretStr("test_token"))
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

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
        self.mock_di.invoker = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id)

        resolver = ToolChoiceResolver(self.mock_di)

        with self.assertRaises(ToolResolutionError) as context:
            resolver.require_tool(ToolType.chat)

        error_message = str(context.exception)
        self.assertIn("Unable to resolve a tool for 'chat'", error_message)
        self.assertIn(str(self.mock_di.invoker.id.hex), error_message)

    def test_user_tool_choice_mapping_through_public_interface(self):
        resolved_1 = stubs.domain.resolved_token(token = SecretStr("test_token_1"))
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved_1
        self.mock_di.invoker = stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_vision = GPT_5_6_TERRA.id,
        )

        resolver = ToolChoiceResolver(self.mock_di)

        chat_result = resolver.get_tool(ToolType.chat)
        self.assertIsNotNone(chat_result)
        assert chat_result is not None
        self.assertIsInstance(chat_result, ConfiguredTool)
        self.assertEqual(chat_result.definition, CLAUDE_4_6_SONNET)
        self.assertEqual(chat_result.token.get_secret_value(), "test_token_1")
        self.assertEqual(chat_result.purpose, ToolType.chat)

        resolved_2 = stubs.domain.resolved_token(token = SecretStr("test_token_2"))
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = resolved_2

        vision_result = resolver.get_tool(ToolType.vision)
        self.assertIsNotNone(vision_result)
        assert vision_result is not None
        self.assertIsInstance(vision_result, ConfiguredTool)
        self.assertEqual(vision_result.definition, GPT_5_6_TERRA)
        self.assertEqual(vision_result.token.get_secret_value(), "test_token_2")
        self.assertEqual(vision_result.purpose, ToolType.vision)

        stock_result = resolver.get_tool(ToolType.api_stock_quote)
        self.assertIsNotNone(stock_result)
        assert stock_result is not None
        self.assertEqual(stock_result.definition, TWELVE_DATA_STOCK_QUOTE)
        self.assertEqual(stock_result.purpose, ToolType.api_stock_quote)

        video_result = resolver.get_tool(ToolType.videos_gen)
        self.assertIsNotNone(video_result)
        assert video_result is not None
        self.assertEqual(video_result.definition, VIDEO_GEN_P_VIDEO)
        self.assertEqual(video_result.purpose, ToolType.videos_gen)
