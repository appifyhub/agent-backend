import unittest
from time import sleep
from unittest.mock import Mock
from uuid import UUID

from langchain_core.messages import AIMessage

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.chat_model_usage_tracking_decorator import (
    ChatModelUsageTrackingDecorator,
    RunnableUsageTrackingDecorator,
)
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ToolType


class ChatModelUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_model = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_text_model = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 10.0))
        self.mock_spending_service = Mock(spec = SpendingService)
        self.tool_purpose = ToolType.chat
        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "test-tool"

        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = self.tool_purpose
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = ChatModelUsageTrackingDecorator(
            wrapped_model = self.mock_model,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            max_tokens = 4096,
        )

    def test_invoke_tracks_usage(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
            },
        }
        mock_response.usage_metadata = None

        self.mock_model.invoke = Mock(return_value = mock_response)

        result = self.decorator.invoke("test input")

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertEqual(call_args.kwargs["tool"], self.external_tool)
        self.assertEqual(call_args.kwargs["tool_purpose"], self.tool_purpose)
        self.assertEqual(call_args.kwargs["input_tokens"], 100)
        self.assertEqual(call_args.kwargs["output_tokens"], 200)
        self.assertEqual(call_args.kwargs["total_tokens"], 300)
        self.assertIsNotNone(call_args.kwargs["runtime_seconds"])
        self.assertGreater(call_args.kwargs["runtime_seconds"], 0)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_invoke_measures_runtime(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {}
        mock_response.usage_metadata = None

        def slow_invoke(*args, **kwargs):
            sleep(0.01)
            return mock_response

        self.mock_model.invoke = slow_invoke

        self.decorator.invoke("test input")

        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_invoke_passes_arguments_correctly(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {}
        mock_response.usage_metadata = None

        self.mock_model.invoke = Mock(return_value = mock_response)

        self.decorator.invoke("test input", {"temperature": 0.7}, stream = False)

        self.mock_model.invoke.assert_called_once_with("test input", {"temperature": 0.7}, stream = False)

    def test_bind_tools_returns_wrapped_runnable(self):
        mock_runnable = Mock()
        self.mock_model.bind_tools = Mock(return_value = mock_runnable)

        result = self.decorator.bind_tools(["tool1", "tool2"])

        self.assertIsInstance(result, RunnableUsageTrackingDecorator)
        self.mock_model.bind_tools.assert_called_once_with(["tool1", "tool2"])

    def test_generate_delegates_to_wrapped_model(self):
        self.mock_model._generate = Mock(return_value = "generated")

        result = self.decorator._generate("input")

        self.assertEqual(result, "generated")
        self.mock_model._generate.assert_called_once_with("input")

    def test_llm_type_delegates_to_wrapped_model(self):
        self.mock_model._llm_type = "test_llm_type"

        result = self.decorator._llm_type

        self.assertEqual(result, "test_llm_type")

    def test_invoke_calls_validate_pre_flight(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {}
        mock_response.usage_metadata = None
        self.mock_model.invoke = Mock(return_value = mock_response)

        self.decorator.invoke("test input")

        self.mock_spending_service.validate_pre_flight.assert_called_once()

    def test_bind_tools_runnable_calls_validate_pre_flight(self):
        mock_runnable = Mock()
        self.mock_model.bind_tools = Mock(return_value = mock_runnable)
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {}
        mock_response.usage_metadata = None
        mock_runnable.invoke = Mock(return_value = mock_response)

        runnable = self.decorator.bind_tools(["tool1"])
        runnable.invoke("test input")

        self.mock_spending_service.validate_pre_flight.assert_called_once()

    def test_invoke_failure_tracks_without_deduction(self):
        self.mock_model.invoke = Mock(side_effect = RuntimeError("API error"))

        with self.assertRaises(RuntimeError):
            self.decorator.invoke("test input")

        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()


class RunnableUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_runnable = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_text_model = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 10.0))
        self.mock_spending_service = Mock(spec = SpendingService)
        self.tool_purpose = ToolType.chat
        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "test-tool"

        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = self.tool_purpose
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = RunnableUsageTrackingDecorator(
            wrapped_runnable = self.mock_runnable,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            max_tokens = 4096,
        )

    def test_invoke_tracks_usage(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {
            "usage": {
                "input_tokens": 50,
                "output_tokens": 100,
                "total_tokens": 150,
            },
        }
        mock_response.usage_metadata = None

        self.mock_runnable.invoke = Mock(return_value = mock_response)

        result = self.decorator.invoke("test input")

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertEqual(call_args.kwargs["tool"], self.external_tool)
        self.assertEqual(call_args.kwargs["tool_purpose"], self.tool_purpose)
        self.assertEqual(call_args.kwargs["input_tokens"], 50)
        self.assertEqual(call_args.kwargs["output_tokens"], 100)
        self.assertEqual(call_args.kwargs["total_tokens"], 150)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_invoke_measures_runtime(self):
        mock_response = Mock(spec = AIMessage)
        mock_response.response_metadata = {}
        mock_response.usage_metadata = None

        def slow_invoke(*args, **kwargs):
            sleep(0.01)
            return mock_response

        self.mock_runnable.invoke = slow_invoke

        self.decorator.invoke("test input")

        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_invoke_failure_tracks_without_deduction(self):
        self.mock_runnable.invoke = Mock(side_effect = RuntimeError("API error"))

        with self.assertRaises(RuntimeError):
            self.decorator.invoke("test input")

        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()
