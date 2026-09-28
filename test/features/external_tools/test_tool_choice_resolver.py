from unittest import TestCase

import stubs
from pydantic import SecretStr
from util.di_utils import di_for_tests

from di.di import DI
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_6_SONNET,
    GPT_5_6_TERRA,
    TWELVE_DATA_STOCK_QUOTE,
    VIDEO_GEN_P_VIDEO,
)
from features.external_tools.tool_choice_resolver import ToolChoiceResolver, ToolResolutionError


class ToolChoiceResolverTest(TestCase):

    di: DI
    resolver: ToolChoiceResolver

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.resolver = self.di.tool_choice_resolver

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
        user = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id, anthropic_key = SecretStr("test_token"))
        self.di.inject_invoker(user)

        result = self.resolver.get_tool(ToolType.chat)

        self.assertEqual(result, stubs.domain.configured_tool(
            definition = CLAUDE_4_6_SONNET,
            token = user.anthropic_key,
            purpose = ToolType.chat,
            payer_id = user.id,
        ))

    def test_get_tool_success_user_no_access_to_user_choice_but_has_access_to_others(self):
        self.di.inject_invoker(stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            anthropic_key = None,
            open_ai_key = SecretStr("test_token"),
            credit_balance = 0,
        ))

        result = self.resolver.get_tool(ToolType.chat)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotEqual(result.definition, CLAUDE_4_6_SONNET)
        self.assertIn(ToolType.chat, result.definition.types)
        self.assertEqual(result.token.get_secret_value(), "test_token")
        self.assertEqual(result.purpose, ToolType.chat)

    def test_get_tool_success_with_default_tool_prioritized(self):
        user = stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            anthropic_key = None,
            open_ai_key = SecretStr("test_token"),
            credit_balance = 0,
        )
        self.di.inject_invoker(user)

        result = self.resolver.get_tool(ToolType.chat, default_tool = GPT_5_6_TERRA.id)

        self.assertEqual(result, stubs.domain.configured_tool(
            definition = GPT_5_6_TERRA,
            token = user.open_ai_key,
            purpose = ToolType.chat,
            payer_id = user.id,
        ))

    def test_get_tool_failure_no_access_to_any_tool(self):
        self.di.inject_invoker(stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            x_ai_key = None,
            credit_balance = 0,
        ))

        result = self.resolver.get_tool(ToolType.chat)

        self.assertIsNone(result)

    def test_require_tool_success(self):
        user = stubs.domain.user(tool_choice_chat = CLAUDE_4_6_SONNET.id, anthropic_key = SecretStr("test_token"))
        self.di.inject_invoker(user)

        result = self.resolver.require_tool(ToolType.chat)

        self.assertEqual(result, stubs.domain.configured_tool(
            definition = CLAUDE_4_6_SONNET,
            token = user.anthropic_key,
            purpose = ToolType.chat,
            payer_id = user.id,
        ))

    def test_require_tool_failure_raises_exception(self):
        self.di.inject_invoker(stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            x_ai_key = None,
            credit_balance = 0,
        ))

        with self.assertRaises(ToolResolutionError) as context:
            self.resolver.require_tool(ToolType.chat)

        error_message = str(context.exception)
        self.assertIn("Unable to resolve a tool for 'chat'", error_message)
        self.assertIn(self.di.invoker.id.hex, error_message)

    def test_user_tool_choice_mapping_through_public_interface(self):
        user = stubs.domain.user(
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_vision = GPT_5_6_TERRA.id,
            anthropic_key = SecretStr("test_token_1"),
            open_ai_key = SecretStr("test_token_2"),
        )
        self.di.inject_invoker(user)

        for purpose, definition, token in (
            (ToolType.chat, CLAUDE_4_6_SONNET, user.anthropic_key),
            (ToolType.vision, GPT_5_6_TERRA, user.open_ai_key),
            (ToolType.api_stock_quote, TWELVE_DATA_STOCK_QUOTE, user.twelve_data_api_key),
            (ToolType.videos_gen, VIDEO_GEN_P_VIDEO, user.replicate_key),
        ):
            with self.subTest(purpose = purpose):
                result = self.resolver.get_tool(purpose)

                self.assertEqual(result, stubs.domain.configured_tool(
                    definition = definition,
                    token = token,
                    purpose = purpose,
                    payer_id = user.id,
                ))
