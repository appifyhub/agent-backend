import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, PERPLEXITY
from features.web_browsing.ai_web_search import AIWebSearch
from util.errors import ConfigurationError, ExternalServiceError


def _make_provider(provider_obj: ExternalToolProvider) -> ConfiguredTool:
    tool = ExternalTool(
        id = "test-model",
        name = "Test Model",
        provider = provider_obj,
        types = [ToolType.search],
        cost_estimate = CostEstimate(
            input_1m_tokens = 100,
            output_1m_tokens = 200,
            web_search_query = 1.4,
        ),
    )
    from uuid import UUID
    return ConfiguredTool(
        definition = tool,
        token = Mock(get_secret_value = lambda: "test-token"),
        purpose = ToolType.search,
        payer_id = UUID(int = 1),
        uses_credits = False,
    )


def _make_di() -> DI:
    di = Mock(spec = DI)
    di.invoker_chat = Mock()
    return di


class AIWebSearchPerplexityTest(unittest.TestCase):

    def setUp(self):
        self.di = _make_di()
        self.configured_tool = _make_provider(PERPLEXITY)

    @patch("features.web_browsing.ai_web_search.format_sources_from_perplexity", return_value = "\n\nSources:\n- [x](http://s)")
    @patch("features.web_browsing.ai_web_search.prompt_resolvers")
    def test_perplexity_path_returns_ai_message_with_sources(self, mock_resolvers, mock_sources):
        mock_resolvers.sentient_web_search.return_value = "system prompt"
        mock_llm = Mock()
        mock_llm.invoke.return_value = AIMessage(content = "answer text", additional_kwargs = {})
        self.di.chat_langchain_model.return_value = mock_llm

        result = AIWebSearch("query", self.configured_tool, self.di).execute()

        self.assertIsInstance(result, AIMessage)
        self.assertIn("answer text", result.content)
        self.assertIn("Sources:", result.content)

    @patch("features.web_browsing.ai_web_search.format_sources_from_perplexity", return_value = "")
    @patch("features.web_browsing.ai_web_search.prompt_resolvers")
    def test_perplexity_raises_on_empty_content(self, mock_resolvers, mock_sources):
        mock_resolvers.sentient_web_search.return_value = "system prompt"
        mock_llm = Mock()
        mock_llm.invoke.return_value = AIMessage(content = "", additional_kwargs = {})
        self.di.chat_langchain_model.return_value = mock_llm

        with self.assertRaises(ExternalServiceError):
            AIWebSearch("query", self.configured_tool, self.di).execute()


class AIWebSearchGoogleTest(unittest.TestCase):

    def setUp(self):
        self.di = _make_di()
        self.configured_tool = _make_provider(GOOGLE_AI)

    def _make_response(self, text: str = "google answer", query_count: int = 2) -> Mock:
        response = Mock()
        response.text = text
        candidate = Mock()
        candidate.content = Mock()
        candidate.content.parts = [Mock()]
        grounding = Mock()
        grounding.web_search_queries = ["q"] * query_count
        grounding.grounding_chunks = []
        candidate.grounding_metadata = grounding
        response.candidates = [candidate]
        return response

    @patch("features.web_browsing.ai_web_search.format_sources_from_google", return_value = "\n\nSources:\n- [x](http://s)")
    def test_google_path_returns_ai_message_with_sources(self, mock_sources):
        response = self._make_response()
        mock_client = Mock()
        mock_client.models.generate_content.return_value = response
        self.di.google_search_client.return_value = mock_client

        result = AIWebSearch("query", self.configured_tool, self.di).execute()

        self.assertIsInstance(result, AIMessage)
        self.assertIn("google answer", result.content)
        self.assertIn("Sources:", result.content)

    @patch("features.web_browsing.ai_web_search.format_sources_from_google", return_value = "")
    def test_google_uses_search_client(self, mock_sources):
        response = self._make_response()
        mock_client = Mock()
        mock_client.models.generate_content.return_value = response
        self.di.google_search_client.return_value = mock_client

        AIWebSearch("query", self.configured_tool, self.di).execute()

        self.di.google_search_client.assert_called_once_with(self.configured_tool)

    @patch("features.web_browsing.ai_web_search.format_sources_from_google", return_value = "")
    def test_google_raises_on_no_candidates(self, mock_sources):
        response = Mock()
        response.candidates = []
        mock_client = Mock()
        mock_client.models.generate_content.return_value = response
        self.di.google_search_client.return_value = mock_client

        with self.assertRaises(ExternalServiceError):
            AIWebSearch("query", self.configured_tool, self.di).execute()

    @patch("features.web_browsing.ai_web_search.format_sources_from_google", return_value = "")
    def test_google_raises_on_empty_answer(self, mock_sources):
        response = self._make_response(text = "")
        mock_client = Mock()
        mock_client.models.generate_content.return_value = response
        self.di.google_search_client.return_value = mock_client

        with self.assertRaises(ExternalServiceError):
            AIWebSearch("query", self.configured_tool, self.di).execute()


class AIWebSearchProviderBranchingTest(unittest.TestCase):

    def test_unsupported_provider_raises_configuration_error(self):
        unknown_provider = ExternalToolProvider(
            id = "unknown",
            name = "Unknown",
            token_management_url = "https://x.com",
            token_format = "x",
            tools = [],
        )
        tool = ExternalTool(
            id = "m",
            name = "M",
            provider = unknown_provider,
            types = [ToolType.search],
            cost_estimate = CostEstimate(),
        )
        from uuid import UUID
        configured = ConfiguredTool(
            definition = tool,
            token = Mock(get_secret_value = lambda: "t"),
            purpose = ToolType.search,
            payer_id = UUID(int = 1),
            uses_credits = False,
        )
        with self.assertRaises(ConfigurationError):
            AIWebSearch("q", configured, _make_di()).execute()
