import unittest
from time import sleep
from unittest.mock import Mock, patch
from uuid import UUID

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators import replicate_usage_tracking_decorator
from features.accounting.usage.decorators.replicate_usage_tracking_decorator import (
    PredictionUsageTrackingDecorator,
    ReplicateUsageTrackingDecorator,
)
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ToolType
from util.errors import ExternalServiceError


class ReplicateUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_client = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_image_model = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 10.0))
        self.mock_spending_service = Mock(spec = SpendingService)
        self.tool_purpose = ToolType.images_edit
        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "test-tool"
        self.image_size = "512x512"

        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = self.tool_purpose
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = ReplicateUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            output_image_sizes = [self.image_size],
        )

    def test_predictions_property_returns_proxy(self):
        predictions = self.decorator.predictions

        self.assertIsNotNone(predictions)

    def test_create_returns_wrapped_prediction(self):
        mock_prediction = Mock()
        self.mock_client.predictions.create = Mock(return_value = mock_prediction)

        result = self.decorator.predictions.create(input = {"prompt": "test"})

        self.assertIsInstance(result, PredictionUsageTrackingDecorator)
        self.mock_client.predictions.create.assert_called_once_with(input = {"prompt": "test"})

    def test_other_predictions_methods_pass_through(self):
        self.mock_client.predictions.list = Mock(return_value = ["pred1", "pred2"])

        result = self.decorator.predictions.list()

        self.assertEqual(result, ["pred1", "pred2"])

    def test_client_attributes_pass_through(self):
        self.mock_client.some_attribute = "test_value"

        result = self.decorator.some_attribute

        self.assertEqual(result, "test_value")

    def test_create_calls_validate_pre_flight(self):
        mock_prediction = Mock()
        self.mock_client.predictions.create = Mock(return_value = mock_prediction)

        self.decorator.predictions.create(input = {"prompt": "test"})

        self.mock_spending_service.validate_pre_flight.assert_called_once()

    def test_video_create_preflights_mapped_size_and_duration_and_returns_wrapped_prediction(self):
        mock_prediction = Mock()
        self.mock_client.predictions.create = Mock(return_value = mock_prediction)
        decorator = ReplicateUsageTrackingDecorator(
            wrapped_client = self.mock_client,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
        )

        prediction = decorator.predictions.create(input = {"prompt": "test"})

        self.assertIsInstance(prediction, PredictionUsageTrackingDecorator)
        self.mock_spending_service.validate_pre_flight.assert_called_once_with(
            self.mock_configured_tool,
            input_image_sizes = None,
            output_image_sizes = None,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
        )


class PredictionUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_prediction = Mock()
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_image_model = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 10.0))
        self.mock_tracking_service.track_video_model = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 20.0))
        self.mock_spending_service = Mock(spec = SpendingService)
        self.tool_purpose = ToolType.images_edit
        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "test-tool"
        self.image_size = "512x512"

        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = self.tool_purpose
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = PredictionUsageTrackingDecorator(
            wrapped_prediction = self.mock_prediction,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            output_image_sizes = [self.image_size],
        )

    def _video_decorator(self) -> PredictionUsageTrackingDecorator:
        return PredictionUsageTrackingDecorator(
            wrapped_prediction = self.mock_prediction,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
        )

    def test_wait_tracks_usage(self):
        self.mock_prediction.metrics = Mock()
        self.mock_prediction.metrics.predict_time = 1.5
        self.mock_prediction.wait = Mock(return_value = "result")

        result = self.decorator.wait()

        self.assertEqual(result, "result")
        self.mock_tracking_service.track_image_model.assert_called_once()
        call_args = self.mock_tracking_service.track_image_model.call_args
        self.assertEqual(call_args.kwargs["tool"], self.external_tool)
        self.assertEqual(call_args.kwargs["tool_purpose"], self.tool_purpose)
        self.assertEqual(call_args.kwargs["output_image_sizes"], [self.image_size])
        self.assertEqual(call_args.kwargs["remote_runtime_seconds"], 1.5)
        self.assertIsNotNone(call_args.kwargs["runtime_seconds"])
        self.assertGreater(call_args.kwargs["runtime_seconds"], 0)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_wait_measures_runtime(self):
        self.mock_prediction.metrics = None

        def slow_wait():
            sleep(0.01)
            return "result"

        self.mock_prediction.wait = slow_wait

        self.decorator.wait()

        call_args = self.mock_tracking_service.track_image_model.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_wait_with_no_metrics(self):
        self.mock_prediction.metrics = None
        self.mock_prediction.wait = Mock(return_value = "result")

        self.decorator.wait()

        call_args = self.mock_tracking_service.track_image_model.call_args
        self.assertIsNone(call_args.kwargs["remote_runtime_seconds"])

    def test_wait_tracks_only_once(self):
        self.mock_prediction.metrics = None
        self.mock_prediction.wait = Mock(return_value = None)

        self.decorator.wait()
        self.decorator.wait()

        self.mock_prediction.wait.assert_called_once_with()
        self.assertEqual(self.mock_tracking_service.track_image_model.call_count, 1)

    def test_wait_with_non_numeric_gpu_time(self):
        self.mock_prediction.metrics = Mock()
        self.mock_prediction.metrics.predict_time = "not_a_number"
        self.mock_prediction.wait = Mock(return_value = "result")

        self.decorator.wait()

        call_args = self.mock_tracking_service.track_image_model.call_args
        self.assertIsNone(call_args.kwargs["remote_runtime_seconds"])

    def test_prediction_attributes_pass_through(self):
        self.mock_prediction.status = "succeeded"

        result = self.decorator.status

        self.assertEqual(result, "succeeded")

    def test_wait_failure_is_cached_and_tracks_without_deduction(self):
        error = RuntimeError("Prediction failed")
        self.mock_prediction.wait = Mock(side_effect = error)

        with self.assertRaises(RuntimeError) as first_context:
            self.decorator.wait()
        with self.assertRaises(RuntimeError) as second_context:
            self.decorator.wait()

        self.assertIs(first_context.exception, error)
        self.assertIs(second_context.exception, error)
        self.mock_prediction.wait.assert_called_once_with()
        self.mock_tracking_service.track_image_model.assert_called_once()
        call_args = self.mock_tracking_service.track_image_model.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()

    def test_video_wait_polls_to_success_and_tracks_mapped_output(self):
        self.mock_prediction.status = "processing"
        self.mock_prediction.metrics = None
        self.mock_prediction.reload.side_effect = lambda: setattr(self.mock_prediction, "status", "succeeded")

        with patch.object(replicate_usage_tracking_decorator, "sleep"):
            result = self._video_decorator().wait()

        self.assertIsNone(result)
        self.mock_prediction.wait.assert_not_called()
        self.mock_prediction.reload.assert_called_once_with()
        self.mock_tracking_service.track_video_model.assert_called_once()
        tracking_args = self.mock_tracking_service.track_video_model.call_args.kwargs
        self.assertEqual(tracking_args["output_video_size"], "2K")
        self.assertEqual(tracking_args["output_video_duration_seconds"], 10)
        self.assertNotIn("is_failed", tracking_args)
        self.mock_spending_service.deduct.assert_called_once_with(self.mock_configured_tool, 20.0)

    def test_video_wait_tracks_terminal_failure_without_deduction(self):
        self.mock_prediction.status = "failed"
        self.mock_prediction.error = "provider failure"
        self.mock_prediction.logs = None
        self.mock_prediction.metrics = None

        with self.assertRaises(ExternalServiceError) as context:
            self._video_decorator().wait()

        self.assertIn("status 'failed': provider failure", str(context.exception))
        self.mock_prediction.reload.assert_not_called()
        self.assertTrue(self.mock_tracking_service.track_video_model.call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()

    def test_video_wait_cancels_and_tracks_timeout_without_deduction(self):
        self.mock_prediction.status = "processing"
        self.mock_prediction.id = "prediction-id"
        self.mock_prediction.metrics = None

        with patch.object(
            replicate_usage_tracking_decorator,
            "monotonic",
            side_effect = [0, 600],
        ):
            with self.assertRaises(ExternalServiceError) as context:
                self._video_decorator().wait()

        self.assertIn("timed out", str(context.exception))
        self.mock_prediction.cancel.assert_called_once_with()
        self.mock_prediction.reload.assert_not_called()
        self.assertTrue(self.mock_tracking_service.track_video_model.call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()
