import unittest
from time import sleep
from unittest.mock import Mock
from uuid import UUID

from google.genai.types import GenerateContentResponse

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.google_search_usage_tracking_decorator import GoogleSearchUsageTrackingDecorator
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ToolType


class GoogleSearchUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_client = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_text_model = Mock(
            return_value = Mock(spec = UsageRecord, total_cost_credits = 2.5),
        )
        self.mock_tracking_service.track_web_search_query = Mock(
            return_value = [Mock(spec = UsageRecord, total_cost_credits = 1.4)],
        )
        self.mock_spending_service = Mock(spec = SpendingService)

        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "gemini-flash-latest"
        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = ToolType.search
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = GoogleSearchUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
        )

    def _make_response(self, query_count: int = 2, candidates_tokens: int = 200, thoughts_tokens: int = 50) -> Mock:
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 10
        response.usage_metadata.candidates_token_count = candidates_tokens
        response.usage_metadata.thoughts_token_count = thoughts_tokens
        response.usage_metadata.total_token_count = 10 + candidates_tokens + thoughts_tokens
        candidate = Mock()
        grounding = Mock()
        grounding.web_search_queries = ["q"] * query_count
        candidate.grounding_metadata = grounding
        response.candidates = [candidate]
        return response

    def test_models_property_returns_proxy(self):
        self.assertIsNotNone(self.decorator.models)

    def test_generate_content_tracks_token_record(self):
        response = self._make_response()
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        self.mock_tracking_service.track_text_model.assert_called_once()
        call_kwargs = self.mock_tracking_service.track_text_model.call_args.kwargs
        self.assertEqual(call_kwargs["tool"], self.external_tool)
        self.assertEqual(call_kwargs["tool_purpose"], ToolType.search)
        self.assertEqual(call_kwargs["input_tokens"], 10)
        self.assertEqual(call_kwargs["output_tokens"], 250)  # candidates + thoughts
        self.assertFalse(call_kwargs["uses_credits"])

    def test_generate_content_tracks_query_records(self):
        response = self._make_response(query_count = 3)
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        self.mock_tracking_service.track_web_search_query.assert_called_once()
        call_kwargs = self.mock_tracking_service.track_web_search_query.call_args.kwargs
        self.assertEqual(call_kwargs["query_count"], 3)

    def test_generate_content_skips_query_records_when_zero_queries(self):
        response = self._make_response(query_count = 0)
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        self.mock_tracking_service.track_web_search_query.assert_not_called()

    def test_generate_content_deducts_token_and_query_costs(self):
        response = self._make_response(query_count = 2)
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        # 1 deduction for the token record + 1 for the single query record returned by the mock
        self.assertEqual(self.mock_spending_service.deduct.call_count, 2)

    def test_generate_content_calls_validate_pre_flight(self):
        response = self._make_response()
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        self.mock_spending_service.validate_pre_flight.assert_called_once()

    def test_generate_content_measures_runtime(self):
        response = self._make_response()

        def slow_generate(*args, **kwargs):
            sleep(0.01)
            return response

        self.mock_client.models.generate_content = slow_generate

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        call_kwargs = self.mock_tracking_service.track_text_model.call_args.kwargs
        self.assertGreaterEqual(call_kwargs["runtime_seconds"], 0.01)

    def test_generate_content_with_no_usage_metadata(self):
        response = self._make_response()
        response.usage_metadata = None
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        call_kwargs = self.mock_tracking_service.track_text_model.call_args.kwargs
        self.assertIsNone(call_kwargs["input_tokens"])
        self.assertIsNone(call_kwargs["output_tokens"])
        self.assertIsNone(call_kwargs["total_tokens"])

    def test_failure_tracks_without_deduction(self):
        self.mock_client.models.generate_content = Mock(side_effect = RuntimeError("API error"))

        with self.assertRaises(RuntimeError):
            self.decorator.models.generate_content(model = "gemini-flash-latest", contents = "query")

        self.mock_tracking_service.track_text_model.assert_called_once()
        call_kwargs = self.mock_tracking_service.track_text_model.call_args.kwargs
        self.assertTrue(call_kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()

    def test_other_models_methods_pass_through(self):
        self.mock_client.models.list_models = Mock(return_value = ["model1"])

        result = self.decorator.models.list_models()

        self.assertEqual(result, ["model1"])
        self.mock_tracking_service.track_text_model.assert_not_called()

    def test_client_attributes_pass_through(self):
        self.mock_client.some_attribute = "test_value"

        self.assertEqual(self.decorator.some_attribute, "test_value")

    def test_decorator_passes_arguments_to_generate_content(self):
        response = self._make_response()
        self.mock_client.models.generate_content = Mock(return_value = response)

        self.decorator.models.generate_content(
            model = "gemini-flash-latest",
            contents = "query",
            config = {"temperature": 0.5},
        )

        self.mock_client.models.generate_content.assert_called_once_with(
            model = "gemini-flash-latest",
            contents = "query",
            config = {"temperature": 0.5},
        )
