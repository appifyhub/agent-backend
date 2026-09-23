import unittest
from time import sleep
from unittest.mock import Mock

import stubs

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.openai_usage_tracking_decorator import OpenAIUsageTrackingDecorator
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.external_tool import ToolType


class OpenAIUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_client = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_text_model = Mock(
            return_value = stubs.domain.usage_record(total_cost_credits = 10.0),
        )
        self.mock_spending_service = Mock(spec = SpendingService)
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.hearing)

        self.decorator = OpenAIUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

    def test_audio_transcriptions_tracks_usage(self):
        mock_response = Mock()
        mock_response.text = "Transcribed text"
        mock_usage = Mock()
        mock_usage.model_dump.return_value = {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }
        mock_response.usage = mock_usage
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.hearing)
        decorator = OpenAIUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

        self.mock_client.audio.transcriptions.create = Mock(return_value = mock_response)

        result = decorator.audio.transcriptions.create(model = "whisper-1", file = Mock())

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertIs(call_args.kwargs["tool"], configured_tool.definition)
        self.assertEqual(call_args.kwargs["tool_purpose"], ToolType.hearing)
        self.assertEqual(call_args.kwargs["input_tokens"], 100)
        self.assertEqual(call_args.kwargs["output_tokens"], 50)
        self.assertEqual(call_args.kwargs["total_tokens"], 150)
        self.assertIsNotNone(call_args.kwargs["runtime_seconds"])
        self.assertGreater(call_args.kwargs["runtime_seconds"], 0)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_audio_transcriptions_measures_runtime(self):
        mock_response = Mock()
        mock_response.text = "Transcribed text"
        mock_response.usage = Mock()

        def slow_create(*args, **kwargs):
            sleep(0.01)
            return mock_response

        self.mock_client.audio.transcriptions.create = slow_create

        self.decorator.audio.transcriptions.create(model = "whisper-1", file = Mock())

        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_embeddings_tracks_usage(self):
        mock_embedding_data = Mock()
        mock_embedding_data.embedding = [0.1, 0.2, 0.3]

        mock_response = Mock()
        mock_response.data = [mock_embedding_data]
        mock_usage = Mock()
        mock_usage.model_dump.return_value = {
            "prompt_tokens": 50,
            "total_tokens": 50,
        }
        mock_response.usage = mock_usage
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.hearing)
        decorator = OpenAIUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

        self.mock_client.embeddings.create = Mock(return_value = mock_response)

        result = decorator.embeddings.create(model = "text-embedding-3-small", input = "test")

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertIs(call_args.kwargs["tool"], configured_tool.definition)
        self.assertEqual(call_args.kwargs["input_tokens"], 50)
        self.assertEqual(call_args.kwargs["total_tokens"], 50)

    def test_embeddings_measures_runtime(self):
        mock_response = Mock()
        mock_response.data = [Mock()]
        mock_response.usage = Mock()

        def slow_create(*args, **kwargs):
            sleep(0.01)
            return mock_response

        self.mock_client.embeddings.create = slow_create

        self.decorator.embeddings.create(model = "text-embedding-3-small", input = "test")

        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_delegates_other_attributes(self):
        self.mock_client.some_other_attribute = "test_value"

        result = self.decorator.some_other_attribute

        self.assertEqual(result, "test_value")

    def test_audio_transcriptions_calls_validate_pre_flight(self):
        mock_response = Mock()
        mock_response.usage = Mock()
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.hearing)
        decorator = OpenAIUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )
        self.mock_client.audio.transcriptions.create = Mock(return_value = mock_response)

        decorator.audio.transcriptions.create(model = "whisper-1", file = Mock())

        self.mock_spending_service.validate_pre_flight.assert_called_once_with(configured_tool)

    def test_audio_transcriptions_failure_tracks_without_deduction(self):
        self.mock_client.audio.transcriptions.create = Mock(side_effect = RuntimeError("API error"))

        with self.assertRaises(RuntimeError):
            self.decorator.audio.transcriptions.create(model = "whisper-1", file = Mock())

        self.mock_tracking_service.track_text_model.assert_called_once()
        call_args = self.mock_tracking_service.track_text_model.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()
