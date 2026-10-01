from typing import cast
from unittest import TestCase

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_google_ai_client import FakeGoogleAIClient
from fakes.fake_x_ai_client import FakeXAIClient
from langchain_core.messages import AIMessage
from stubs import domain, external
from util.di_utils import di_for_tests
from xai_sdk.proto import chat_pb2

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GEMINI_FLASH_LATEST, GROK_4_3, SONAR
from features.external_tools.external_tool_provider_library import ANTHROPIC
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError


class AIWebSearchPerplexityTest(TestCase):

    di: DI
    tool: ConfiguredTool
    model: FakeChatModel

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.di.inject_invoker_chat(domain.chat_config())
        self.tool = domain.configured_tool(definition = SONAR, purpose = ToolType.search)
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool, max_tokens = 500))

    def test_perplexity_path_returns_ai_message_with_sources(self):
        self.model.responses.append(external.ai_message(
            content = "answer text",
            additional_kwargs = {"search_results": [external.perplexity_search_result()]},
        ))

        result = self.di.ai_web_search("query", self.tool).execute()

        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "answer text\n\nSources:\n- [example.com](https://example.com/short)")
        messages, = self.model.prompts
        self.assertEqual(messages[0].type, "system")
        self.assertTrue(messages[0].content)
        self.assertEqual(messages[1].type, "human")
        self.assertEqual(messages[1].content, "query")

    def test_perplexity_raises_on_empty_content(self):
        self.model.responses.append(external.ai_message(content = ""))

        with self.assertRaises(ExternalServiceError) as raised:
            self.di.ai_web_search("query", self.tool).execute()

        self.assertEqual(raised.exception.error_code, EXTERNAL_EMPTY_RESPONSE)


class AIWebSearchGoogleTest(TestCase):

    di: DI
    tool: ConfiguredTool
    client: FakeGoogleAIClient

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.tool = domain.configured_tool(definition = GEMINI_FLASH_LATEST, purpose = ToolType.search)
        self.client = cast(FakeGoogleAIClient, self.di.base_google_ai_client(self.tool.token.get_secret_value()))

    def test_google_path_returns_ai_message_with_sources(self):
        self.client.models.responses.append(external.google_grounding_response(
            grounding_chunks = [external.google_grounding_chunk()],
        ))

        result = self.di.ai_web_search("query", self.tool).execute()

        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "Google answer\n\nSources:\n- [example.com](https://example.com/short)")
        request, = self.client.models.requests
        self.assertEqual(request["model"], self.tool.definition.id)
        self.assertEqual(request["contents"], "query")
        tool, = request["config"].tools
        self.assertIsNotNone(tool.google_search)

    def test_google_raises_on_no_candidates(self):
        self.client.models.responses.append(external.google_grounding_response(candidates = []))

        with self.assertRaises(ExternalServiceError) as raised:
            self.di.ai_web_search("query", self.tool).execute()

        self.assertEqual(raised.exception.error_code, EXTERNAL_EMPTY_RESPONSE)
        self.assertIn("No candidates", str(raised.exception))

    def test_google_raises_on_empty_answer(self):
        self.client.models.responses.append(external.google_grounding_response(text = ""))

        with self.assertRaises(ExternalServiceError) as raised:
            self.di.ai_web_search("query", self.tool).execute()

        self.assertEqual(raised.exception.error_code, EXTERNAL_EMPTY_RESPONSE)
        self.assertIn("empty answer", str(raised.exception))


class AIWebSearchXAITest(TestCase):

    di: DI
    tool: ConfiguredTool
    client: FakeXAIClient

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(domain.user())
        self.di.inject_invoker_chat(domain.chat_config())
        self.tool = domain.configured_tool(definition = GROK_4_3, purpose = ToolType.search)
        self.client = cast(FakeXAIClient, self.di.base_x_ai_client(self.tool))

    def test_xai_path_uses_both_search_tools(self):
        self.client.chat.responses.append(external.x_ai_chat_response(citations = ["https://example.com/page"]))

        result = self.di.ai_web_search("query", self.tool).execute()

        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "xAI answer\n\nSources:\n- [example.com](https://example.com/short)")
        request, = self.client.chat.requests
        self.assertEqual(request["model"], self.tool.definition.id)
        self.assertEqual(len(request["messages"]), 2)
        self.assertEqual(request["messages"][0].role, chat_pb2.MessageRole.ROLE_SYSTEM)
        self.assertTrue(request["messages"][0].content[0].text)
        self.assertEqual(request["messages"][1].role, chat_pb2.MessageRole.ROLE_USER)
        self.assertEqual(request["messages"][1].content[0].text, "query")
        web_tool, x_tool = request["tools"]
        self.assertTrue(web_tool.HasField("web_search"))
        self.assertTrue(x_tool.HasField("x_search"))
        self.assertEqual(request["include"], ["inline_citations"])

    def test_xai_raises_on_empty_answer(self):
        self.client.chat.responses.append(external.x_ai_chat_response(content = ""))

        with self.assertRaises(ExternalServiceError) as raised:
            self.di.ai_web_search("query", self.tool).execute()

        self.assertEqual(raised.exception.error_code, EXTERNAL_EMPTY_RESPONSE)


class AIWebSearchProviderBranchingTest(TestCase):

    def test_unsupported_provider_raises_configuration_error(self):
        di = self.enterContext(di_for_tests())
        configured = domain.configured_tool(
            definition = domain.external_tool(provider = ANTHROPIC, types = [ToolType.search]),
            purpose = ToolType.search,
        )

        with self.assertRaises(ConfigurationError) as raised:
            di.ai_web_search("query", configured).execute()

        self.assertEqual(raised.exception.error_code, UNSUPPORTED_PROVIDER)
