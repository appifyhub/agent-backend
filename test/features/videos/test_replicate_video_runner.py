import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from pydantic import SecretStr

from di.di import DI
from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.replicate_usage_tracking_decorator import ReplicateUsageTrackingDecorator
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import VIDEO_GEN_P_VIDEO
from features.videos import replicate_video_runner
from features.videos.video_api_utils import map_to_model_parameters
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, INSUFFICIENT_CREDITS, VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ValidationError


class ReplicateVideoRunnerTest(unittest.TestCase):

    def setUp(self):
        self.invoker_id = UUID(int = 1)
        self.invoker_chat_id = UUID(int = 2)
        self.payer_id = UUID(int = 3)
        self.configured_tool = ConfiguredTool(
            definition = VIDEO_GEN_P_VIDEO,
            token = SecretStr("replicate-token"),
            purpose = ToolType.videos_gen,
            payer_id = self.payer_id,
            uses_credits = True,
        )
        self.reference_urls = [
            "https://example.com/first.png",
            "https://example.com/ignored.png",
        ]
        self.parameters = map_to_model_parameters(
            VIDEO_GEN_P_VIDEO,
            prompt = "make them shake hands",
            duration = "long",
            aspect_ratio = "9:16",
            output_size = "4K",
            reference_image_urls = self.reference_urls,
        )

        self.prediction = Mock()
        self.prediction.id = "prediction-id"
        self.prediction.status = "succeeded"
        self.prediction.output = "https://example.com/output.mp4"
        self.prediction.error = None
        self.prediction.logs = None
        self.prediction.metrics = Mock(predict_time = 2.5)

        self.base_client = Mock()
        self.base_client.predictions.create.return_value = self.prediction
        self.tracking = Mock(spec = UsageTrackingService)
        self.tracking.track_video_model.return_value = Mock(
            spec = UsageRecord,
            total_cost_credits = 40.0,
        )
        self.spending = Mock(spec = SpendingService)
        self.replicate = ReplicateUsageTrackingDecorator(
            wrapped_client = self.base_client,
            tracking_service = self.tracking,
            spending_service = self.spending,
            configured_tool = self.configured_tool,
            output_video_size = self.parameters.size,
            output_video_duration_seconds = self.parameters.duration,
        )

        self.di = Mock(spec = DI)
        self.di.replicate_client.return_value = self.replicate

    def _run(
        self,
        monotonic_values: list[float] | None = None,
        time_values: list[float] | None = None,
    ) -> str:
        self.session_context = MagicMock()
        self.session_context.__enter__.return_value = Mock()

        with patch(
            "features.videos.replicate_video_runner.get_detached_session",
            return_value = self.session_context,
        ) as mock_get_session, patch(
            "features.videos.replicate_video_runner.DI",
            return_value = self.di,
        ) as mock_di, patch(
            "features.accounting.usage.decorators.replicate_usage_tracking_decorator.monotonic",
            side_effect = monotonic_values or [],
        ), patch(
            "features.accounting.usage.decorators.replicate_usage_tracking_decorator.time",
            side_effect = time_values or [],
        ), patch(
            "features.accounting.usage.decorators.replicate_usage_tracking_decorator.sleep",
        ) as mock_sleep:
            self.mock_get_session = mock_get_session
            self.mock_di = mock_di
            self.mock_sleep = mock_sleep
            return replicate_video_runner.run_replicate_video(
                configured_tool = self.configured_tool,
                parameters = self.parameters,
                invoker_id = self.invoker_id,
                invoker_chat_id = self.invoker_chat_id,
            )

    def test_success_uses_p_video_mapping_preflight_and_terminal_accounting(self):
        result = self._run(monotonic_values = [0], time_values = [0, 5])

        self.assertEqual(result, "https://example.com/output.mp4")
        self.assertEqual(self.parameters.size, "2K")
        self.assertEqual(self.parameters.duration, 10)
        self.assertEqual(
            self.parameters.duration * (VIDEO_GEN_P_VIDEO.cost_estimate.output_video_2k_second or 0),
            40,
        )
        self.di.replicate_client.assert_called_once_with(
            self.configured_tool,
            config.web_timeout_s * 10,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
        )
        self.spending.validate_pre_flight.assert_called_once_with(
            self.configured_tool,
            input_image_sizes = None,
            output_image_sizes = None,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
        )
        self.base_client.predictions.create.assert_called_once_with(
            version = VIDEO_GEN_P_VIDEO.id,
            input = {
                "prompt": "make them shake hands",
                "image": self.reference_urls[0],
                "duration": 10,
                "resolution": "1080p",
                "fps": 24,
                "draft": False,
                "prompt_upsampling": False,
                "disable_safety_filter": True,
                "save_audio": True,
            },
        )
        self.tracking.track_video_model.assert_called_once_with(
            tool = VIDEO_GEN_P_VIDEO,
            tool_purpose = ToolType.videos_gen,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = True,
            output_video_size = "2K",
            output_video_duration_seconds = 10,
            remote_runtime_seconds = 2.5,
        )
        self.spending.deduct.assert_called_once_with(self.configured_tool, 40.0)
        self.di.rollback_db_session.assert_called_once_with()
        self.mock_get_session.assert_called_once_with()

    def test_polling_reloads_after_creation_transaction_rolls_back(self):
        self.prediction.status = "processing"

        def finish_prediction():
            self.assertTrue(self.di.rollback_db_session.called)
            self.assertFalse(self.session_context.__exit__.called)
            self.prediction.status = "succeeded"

        self.prediction.reload.side_effect = finish_prediction

        result = self._run(monotonic_values = [0, 1], time_values = [0, 5])

        self.assertEqual(result, "https://example.com/output.mp4")
        self.prediction.reload.assert_called_once_with()
        self.mock_sleep.assert_called_once_with(5)
        self.mock_di.assert_called_once_with(
            self.session_context.__enter__.return_value,
            self.invoker_id.hex,
            self.invoker_chat_id.hex,
        )
        self.session_context.__exit__.assert_called_once()

    def test_failed_prediction_tracks_without_deduction(self):
        self.prediction.status = "failed"
        self.prediction.error = "provider failed"

        with self.assertRaises(ExternalServiceError) as context:
            self._run(monotonic_values = [0], time_values = [0, 3])

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertIn("provider failed", str(context.exception))
        self.assertTrue(self.tracking.track_video_model.call_args.kwargs["is_failed"])
        self.spending.deduct.assert_not_called()

    def test_canceled_prediction_tracks_without_deduction(self):
        self.prediction.status = "canceled"

        with self.assertRaises(ExternalServiceError) as context:
            self._run(monotonic_values = [0], time_values = [0, 3])

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertTrue(self.tracking.track_video_model.call_args.kwargs["is_failed"])
        self.spending.deduct.assert_not_called()

    def test_succeeded_prediction_with_empty_output_matches_image_accounting_order(self):
        self.prediction.output = None

        with self.assertRaises(ExternalServiceError) as context:
            self._run(monotonic_values = [0], time_values = [0, 3])

        self.assertEqual(context.exception.error_code, EXTERNAL_EMPTY_RESPONSE)
        self.assertNotIn("is_failed", self.tracking.track_video_model.call_args.kwargs)
        self.spending.deduct.assert_called_once_with(self.configured_tool, 40.0)

    def test_timeout_attempts_cancellation_and_tracks_failure(self):
        self.prediction.status = "processing"

        with patch(
            "features.accounting.usage.decorators.replicate_usage_tracking_decorator.VIDEO_PREDICTION_TIMEOUT_SECONDS",
            10,
        ):
            with self.assertRaises(ExternalServiceError) as context:
                self._run(monotonic_values = [0, 10], time_values = [0, 10])

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.prediction.cancel.assert_called_once_with()
        self.prediction.reload.assert_not_called()
        self.mock_sleep.assert_not_called()
        self.assertTrue(self.tracking.track_video_model.call_args.kwargs["is_failed"])
        self.spending.deduct.assert_not_called()

    def test_preflight_failure_does_not_create_or_track_prediction(self):
        self.spending.validate_pre_flight.side_effect = ValidationError(
            "Insufficient credits",
            INSUFFICIENT_CREDITS,
        )

        with self.assertRaises(ValidationError) as context:
            self._run()

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.base_client.predictions.create.assert_not_called()
        self.tracking.track_video_model.assert_not_called()
        self.di.rollback_db_session.assert_not_called()
        self.assertEqual(self.mock_get_session.call_count, 1)

    def test_prediction_creation_failure_is_structured_without_terminal_tracking(self):
        self.base_client.predictions.create.side_effect = RuntimeError("Replicate unavailable")

        with self.assertRaises(ExternalServiceError) as context:
            self._run()

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertIsInstance(context.exception.__cause__, RuntimeError)
        self.tracking.track_video_model.assert_not_called()
        self.di.rollback_db_session.assert_not_called()
        self.assertEqual(self.mock_get_session.call_count, 1)
