from unittest import TestCase

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_perplexity import ChatPerplexity
from stubs import domain
from util.di_utils import di_for_tests

from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_8_OPUS,
    CLAUDE_5_OPUS,
    GPT_5_6_LUNA,
    GPT_5_6_SOL,
    GPT_5_6_TERRA,
)
from features.external_tools.external_tool_provider_library import ANTHROPIC, GOOGLE_AI, OPEN_AI, PERPLEXITY
from features.llm.langchain_factory import create
from util.config import config
from util.errors import ConfigurationError


class LangchainFactoryTest(TestCase):

    def setUp(self):
        # exercise the factory's real model construction under the shared network guard
        self.enterContext(di_for_tests())

    def test_create_openai_chat_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatOpenAI)

    def test_create_gpt_5_6_models_without_reasoning(self):
        for tool in (GPT_5_6_SOL, GPT_5_6_TERRA, GPT_5_6_LUNA):
            with self.subTest(tool = tool.id):
                configured_tool = domain.configured_tool(definition = tool)

                result = create(configured_tool, 4096)

                self.assertEqual(result.reasoning_effort, "none")

    def test_create_anthropic_reasoning_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(
                provider = ANTHROPIC,
                types = [ToolType.chat, ToolType.reasoning],
            ),
            purpose = ToolType.reasoning,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatAnthropic)

    def test_create_current_opus_models_without_temperature(self):
        for tool in (CLAUDE_4_8_OPUS, CLAUDE_5_OPUS):
            with self.subTest(tool = tool.id):
                configured_tool = domain.configured_tool(definition = tool, purpose = ToolType.reasoning)

                result = create(configured_tool, 4096)

                self.assertNotIn("temperature", result.model_fields_set)
                self.assertIsNone(result.temperature)

    def test_create_perplexity_search_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = PERPLEXITY),
            purpose = ToolType.search,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatPerplexity)

    def test_create_google_ai_chat_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = GOOGLE_AI),
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatGoogleGenerativeAI)

    def test_create_copywriting_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.copywriting,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatOpenAI)

    def test_create_vision_model(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = ANTHROPIC),
            purpose = ToolType.vision,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatAnthropic)

    def test_create_unsupported_provider(self):
        unsupported_provider = domain.external_tool_provider(id = "unsupported")

        unsupported_tool = domain.external_tool(provider = unsupported_provider)

        configured_tool = domain.configured_tool(definition = unsupported_tool)

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support temperature", str(context.exception))

    def test_unsupported_tool_type_temperature(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.hearing,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_tool_type_max_tokens(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.images_gen,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_tool_type_timeout(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.embedding,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_provider_temperature_normalization(self):
        unsupported_provider = domain.external_tool_provider(id = "unknown-provider")

        unsupported_tool = domain.external_tool(provider = unsupported_provider)

        configured_tool = domain.configured_tool(definition = unsupported_tool)

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support temperature", str(context.exception))

    def test_all_supported_tool_types_with_openai(self):
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = domain.configured_tool(
                    definition = domain.external_tool(
                        provider = OPEN_AI,
                        types = [ToolType.chat, ToolType.reasoning],
                    ),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatOpenAI)

    def test_all_supported_tool_types_with_anthropic(self):
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = domain.configured_tool(
                    definition = domain.external_tool(provider = ANTHROPIC),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatAnthropic)

    def test_all_supported_tool_types_with_perplexity(self):
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = domain.configured_tool(
                    definition = domain.external_tool(provider = PERPLEXITY),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatPerplexity)

    def test_all_supported_tool_types_with_google_ai(self):
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = domain.configured_tool(
                    definition = domain.external_tool(provider = GOOGLE_AI),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatGoogleGenerativeAI)

    def test_config_values_are_used(self):
        self.addCleanup(setattr, config, "web_retries", config.web_retries)
        self.addCleanup(setattr, config, "web_timeout_s", config.web_timeout_s)
        config.web_retries = 7
        config.web_timeout_s = 42

        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
        )

        result = create(configured_tool, 4096)

        self.assertEqual(result.max_retries, 7)
        self.assertEqual(result.request_timeout, 42)
        self.assertEqual(result.max_tokens, 4096)
        self.assertEqual(result.model_name, configured_tool.definition.id)
        self.assertEqual(result.openai_api_key, configured_tool.token)

    def test_temperature_calculation_logic(self):
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
        )
        chat_result = create(configured_tool, 4096)
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(
                provider = OPEN_AI,
                types = [ToolType.chat, ToolType.reasoning],
            ),
            purpose = ToolType.reasoning,
        )
        reasoning_result = create(configured_tool, 4096)
        configured_tool = domain.configured_tool(
            definition = domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.copywriting,
        )
        copywriting_result = create(configured_tool, 4096)

        self.assertEqual(chat_result.temperature, 0.5)
        self.assertEqual(reasoning_result.temperature, 0.5)
        self.assertEqual(copywriting_result.temperature, 0.8)

    def test_reasoning_tool_has_longer_timeout(self):
        self.addCleanup(setattr, config, "web_timeout_s", config.web_timeout_s)
        config.web_timeout_s = 10

        # [1] chat requested, tool supports reasoning -> 3x timeout
        configured_tool_chat = domain.configured_tool(
            definition = domain.external_tool(
                provider = OPEN_AI,
                types = [ToolType.chat, ToolType.reasoning],
            ),
        )
        result_chat = create(configured_tool_chat, 4096)
        self.assertEqual(result_chat.request_timeout, 30)  # 10 * 3

        # [2] reasoning requested -> 3x timeout
        configured_tool_reasoning = domain.configured_tool(
            definition = domain.external_tool(
                provider = OPEN_AI,
                types = [ToolType.chat, ToolType.reasoning],
            ),
            purpose = ToolType.reasoning,
        )
        result_reasoning = create(configured_tool_reasoning, 4096)
        self.assertEqual(result_reasoning.request_timeout, 30)  # 10 * 3

        # [3] chat requested, tool does not support reasoning -> 1x timeout
        chat_only_tool = domain.external_tool(provider = OPEN_AI)
        configured_tool_chat_only = domain.configured_tool(definition = chat_only_tool)
        result_chat_only = create(configured_tool_chat_only, 4096)
        self.assertEqual(result_chat_only.request_timeout, 10)  # 10 * 1
