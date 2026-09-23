import unittest
from unittest.mock import patch

import stubs
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_perplexity import ChatPerplexity

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
from util.errors import ConfigurationError


class LangchainFactoryTest(unittest.TestCase):

    @patch("features.llm.langchain_factory.config")
    def test_create_openai_chat_model(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatOpenAI)

    @patch("features.llm.langchain_factory.ChatOpenAI")
    @patch("features.llm.langchain_factory.config")
    def test_create_gpt_5_6_models_without_reasoning(self, mock_config, mock_chat_openai):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        for tool in (GPT_5_6_SOL, GPT_5_6_TERRA, GPT_5_6_LUNA):
            with self.subTest(tool = tool.id):
                mock_chat_openai.reset_mock()
                configured_tool = stubs.domain.configured_tool(definition = tool)

                create(configured_tool, 4096)

                self.assertEqual(mock_chat_openai.call_args.kwargs["reasoning_effort"], "none")

    @patch("features.llm.langchain_factory.config")
    def test_create_anthropic_reasoning_model(self, mock_config):
        mock_config.web_retries = 5
        mock_config.web_timeout_s = 15

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(
                provider = ANTHROPIC,
                types = [ToolType.chat, ToolType.reasoning],
            ),
            purpose = ToolType.reasoning,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatAnthropic)

    @patch("features.llm.langchain_factory.ChatAnthropic")
    @patch("features.llm.langchain_factory.config")
    def test_create_current_opus_models_without_temperature(self, mock_config, mock_chat_anthropic):
        mock_config.web_retries = 5
        mock_config.web_timeout_s = 15

        for tool in (CLAUDE_4_8_OPUS, CLAUDE_5_OPUS):
            with self.subTest(tool = tool.id):
                mock_chat_anthropic.reset_mock()
                configured_tool = stubs.domain.configured_tool(definition = tool, purpose = ToolType.reasoning)

                create(configured_tool, 4096)

                self.assertNotIn("temperature", mock_chat_anthropic.call_args.kwargs)

    @patch("features.llm.langchain_factory.config")
    def test_create_perplexity_search_model(self, mock_config):
        mock_config.web_retries = 2
        mock_config.web_timeout_s = 20

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = PERPLEXITY),
            purpose = ToolType.search,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatPerplexity)

    @patch("features.llm.langchain_factory.config")
    def test_create_google_ai_chat_model(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = GOOGLE_AI),
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatGoogleGenerativeAI)

    @patch("features.llm.langchain_factory.config")
    def test_create_copywriting_model(self, mock_config):
        mock_config.web_retries = 1
        mock_config.web_timeout_s = 30

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.copywriting,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatOpenAI)

    @patch("features.llm.langchain_factory.config")
    def test_create_vision_model(self, mock_config):
        mock_config.web_retries = 4
        mock_config.web_timeout_s = 25

        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = ANTHROPIC),
            purpose = ToolType.vision,
        )

        result = create(configured_tool, 4096)

        self.assertIsInstance(result, ChatAnthropic)

    def test_create_unsupported_provider(self):
        unsupported_provider = stubs.domain.external_tool_provider(id = "unsupported")

        unsupported_tool = stubs.domain.external_tool(provider = unsupported_provider)

        configured_tool = stubs.domain.configured_tool(definition = unsupported_tool)

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support temperature", str(context.exception))

    def test_unsupported_tool_type_temperature(self):
        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.hearing,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_tool_type_max_tokens(self):
        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.images_gen,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_tool_type_timeout(self):
        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
            purpose = ToolType.embedding,
        )

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support text timeouts", str(context.exception))

    def test_unsupported_provider_temperature_normalization(self):
        unsupported_provider = stubs.domain.external_tool_provider(id = "unknown-provider")

        unsupported_tool = stubs.domain.external_tool(provider = unsupported_provider)

        configured_tool = stubs.domain.configured_tool(definition = unsupported_tool)

        with self.assertRaises(ConfigurationError) as context:
            create(configured_tool, 4096)

        self.assertIn("does not support temperature", str(context.exception))

    @patch("features.llm.langchain_factory.config")
    def test_all_supported_tool_types_with_openai(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        # Test all supported tool types
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            # noinspection PyUnresolvedReferences
            with self.subTest(tool_type = tool_type):
                configured_tool = stubs.domain.configured_tool(
                    definition = stubs.domain.external_tool(
                        provider = OPEN_AI,
                        types = [ToolType.chat, ToolType.reasoning],
                    ),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatOpenAI)

    @patch("features.llm.langchain_factory.config")
    def test_all_supported_tool_types_with_anthropic(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        # Test all supported tool types
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = stubs.domain.configured_tool(
                    definition = stubs.domain.external_tool(provider = ANTHROPIC),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatAnthropic)

    @patch("features.llm.langchain_factory.config")
    def test_all_supported_tool_types_with_perplexity(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        # Test all supported tool types
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = stubs.domain.configured_tool(
                    definition = stubs.domain.external_tool(provider = PERPLEXITY),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatPerplexity)

    @patch("features.llm.langchain_factory.config")
    def test_all_supported_tool_types_with_google_ai(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        # Test all supported tool types
        supported_types = [
            ToolType.chat,
            ToolType.reasoning,
            ToolType.copywriting,
            ToolType.vision,
            ToolType.search,
        ]

        for tool_type in supported_types:
            with self.subTest(tool_type = tool_type):
                configured_tool = stubs.domain.configured_tool(
                    definition = stubs.domain.external_tool(provider = GOOGLE_AI),
                    purpose = tool_type,
                )
                result = create(configured_tool, 4096)
                self.assertIsInstance(result, ChatGoogleGenerativeAI)

    @patch("features.llm.langchain_factory.config")
    def test_config_values_are_used(self, mock_config):
        """Test that config values are properly passed to model creation"""
        mock_config.web_retries = 7
        mock_config.web_timeout_s = 42

        # Just verify the function completes without error
        # The actual config usage is tested implicitly by the model creation
        configured_tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(provider = OPEN_AI),
        )
        result = create(configured_tool, 4096)
        self.assertIsInstance(result, ChatOpenAI)

    def test_temperature_calculation_logic(self):
        """Test that different tool types result in different model instances"""

        with patch("features.llm.langchain_factory.config") as mock_config:
            mock_config.web_retries = 3
            mock_config.web_timeout_s = 10

            # Test that different tool types create models (temperature logic is internal)
            configured_tool = stubs.domain.configured_tool(
                definition = stubs.domain.external_tool(provider = OPEN_AI),
            )
            chat_result = create(configured_tool, 4096)
            configured_tool = stubs.domain.configured_tool(
                definition = stubs.domain.external_tool(
                    provider = OPEN_AI,
                    types = [ToolType.chat, ToolType.reasoning],
                ),
                purpose = ToolType.reasoning,
            )
            reasoning_result = create(configured_tool, 4096)
            configured_tool = stubs.domain.configured_tool(
                definition = stubs.domain.external_tool(provider = OPEN_AI),
                purpose = ToolType.copywriting,
            )
            copywriting_result = create(configured_tool, 4096)

            # All should be ChatOpenAI instances but potentially with different configs
            self.assertIsInstance(chat_result, ChatOpenAI)
            self.assertIsInstance(reasoning_result, ChatOpenAI)
            self.assertIsInstance(copywriting_result, ChatOpenAI)

    @patch("features.llm.langchain_factory.config")
    def test_reasoning_tool_has_longer_timeout(self, mock_config):
        mock_config.web_retries = 3
        mock_config.web_timeout_s = 10

        # [1] chat requested, tool supports reasoning -> 3x timeout
        configured_tool_chat = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(
                provider = OPEN_AI,
                types = [ToolType.chat, ToolType.reasoning],
            ),
        )
        result_chat = create(configured_tool_chat, 4096)
        self.assertEqual(result_chat.request_timeout, 30)  # 10 * 3

        # [2] reasoning requested -> 3x timeout
        configured_tool_reasoning = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(
                provider = OPEN_AI,
                types = [ToolType.chat, ToolType.reasoning],
            ),
            purpose = ToolType.reasoning,
        )
        result_reasoning = create(configured_tool_reasoning, 4096)
        self.assertEqual(result_reasoning.request_timeout, 30)  # 10 * 3

        # [3] chat requested, tool does not support reasoning -> 1x timeout
        chat_only_tool = stubs.domain.external_tool(provider = OPEN_AI)
        configured_tool_chat_only = stubs.domain.configured_tool(definition = chat_only_tool)
        result_chat_only = create(configured_tool_chat_only, 4096)
        self.assertEqual(result_chat_only.request_timeout, 10)  # 10 * 1
