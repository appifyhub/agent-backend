from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_replicate_client import FakeReplicateClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.replicate_usage_tracking_decorator import ReplicateUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import IMAGE_GEN_EDIT_FLUX_2_PRO, VIDEO_GEN_P_VIDEO
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR, VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ValidationError


class ReplicateUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    client: FakeReplicateClient
    decorator: ReplicateUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = IMAGE_GEN_EDIT_FLUX_2_PRO.id),
            purpose = ToolType.images_gen,
            uses_credits = True,
        )
        self.client = cast(FakeReplicateClient, self.di.base_replicate_client(self.tool.token.get_secret_value()))
        self.decorator = self.di.replicate_client(self.tool, output_image_sizes = ["1k"])
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_create_defers_accounting_until_wait_and_exposes_prediction(self):
        response = stubs.external.replicate_prediction(output = ["https://example.com/image.png"], logs = "done")
        self.client.predictions.responses.append(response)

        prediction = self.decorator.predictions.create(input = {"prompt": "test"})

        self.assertEqual(self.client.predictions.requests, [("create", {"input": {"prompt": "test"}})])
        self.assertEqual(prediction.id, response.id)
        self.assertEqual(prediction.output, response.output)
        self.assertEqual(prediction.logs, "done")
        self.assertEqual(prediction.status, "succeeded")
        self.assertIsNone(prediction.error)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_other_prediction_methods_pass_through_without_tracking(self):
        response = stubs.external.replicate_prediction()
        self.client.predictions.updates[response.id].append(response)

        self.assertEqual(self.decorator.predictions.get(response.id), response)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])

    def test_client_attributes_pass_through(self):
        self.assertEqual(self.decorator.poll_interval, self.client.poll_interval)

    def test_create_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))

        with self.assertRaises(ValidationError) as raised:
            self.decorator.predictions.create(input = {"prompt": "test"})

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.predictions.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_video_create_preflights_size_and_duration(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 2.5))
        tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = VIDEO_GEN_P_VIDEO.id),
            purpose = ToolType.videos_gen,
            uses_credits = True,
        )
        decorator = self.di.replicate_client(tool, output_video_size = "2K", output_video_duration_seconds = 10)

        with self.assertRaises(ValidationError) as raised:
            decorator.predictions.create(input = {"prompt": "test"})

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.predictions.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_wait_tracks_usage_and_deducts_credits_once(self):
        initial = stubs.external.replicate_prediction(status = "processing")
        self.client.predictions.responses.append(initial)
        self.client.predictions.updates[initial.id].append(stubs.external.replicate_prediction(
            metrics = {"predict_time": 1.5}, output = ["https://example.com/image.png"],
        ))
        prediction = self.decorator.predictions.create(input = {"prompt": "test"})

        self.assertIsNone(prediction.wait())
        self.assertIsNone(prediction.wait())

        self.assertEqual(prediction.output, ["https://example.com/image.png"])
        self.assertEqual([method for method, _ in self.client.predictions.requests], ["create", "get"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, ToolType.images_gen)
        self.assertEqual(record.output_image_sizes, ["1k"])
        self.assertEqual(record.remote_runtime_seconds, 1.5)
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_wait_measures_runtime(self):
        self.client.predictions.responses.append(stubs.external.replicate_prediction())
        # the wrapper measures from creation through wait; control only the system clock
        with patch("features.accounting.usage.decorators.replicate_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            prediction = self.decorator.predictions.create(input = {"prompt": "test"})
            prediction.wait()

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_wait_without_numeric_metrics(self):
        for metrics in (None, {"predict_time": "not_a_number"}):
            with self.subTest(metrics = metrics):
                self.client.predictions.responses.append(stubs.external.replicate_prediction(metrics = metrics))
                prediction = self.decorator.predictions.create(input = {"prompt": "test"})

                prediction.wait()

                record = self.di.usage_record_repo.get_by_user(self.user.id)[0]
                self.assertIsNone(record.remote_runtime_seconds)

    def test_wait_failure_is_cached_and_tracks_without_deduction(self):
        initial = stubs.external.replicate_prediction(status = "processing")
        error = ExternalServiceError("Prediction failed", UNEXPECTED_ERROR)
        self.client.predictions.responses.append(initial)
        self.client.predictions.updates[initial.id].append(error)
        prediction = self.decorator.predictions.create(input = {"prompt": "test"})

        with self.assertRaises(ExternalServiceError) as first:
            prediction.wait()
        with self.assertRaises(ExternalServiceError) as second:
            prediction.wait()

        self.assertIs(first.exception, error)
        self.assertIs(second.exception, error)
        self.assertEqual([method for method, _ in self.client.predictions.requests], ["create", "get"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_video_wait_polls_to_success_and_tracks_mapped_output(self):
        initial = stubs.external.replicate_prediction(status = "processing")
        self.client.predictions.responses.append(initial)
        self.client.predictions.updates[initial.id].append(stubs.external.replicate_prediction(
            output = "https://example.com/video.mp4",
        ))
        tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = VIDEO_GEN_P_VIDEO.id),
            purpose = ToolType.videos_gen,
            uses_credits = True,
        )
        decorator = self.di.replicate_client(tool, output_video_size = "2K", output_video_duration_seconds = 10)
        prediction = decorator.predictions.create(input = {"prompt": "test"})

        # skip the system polling delay while real prediction reloads consume fake client responses
        with patch("features.accounting.usage.decorators.replicate_usage_tracking_decorator.sleep"):
            result = prediction.wait()

        self.assertIsNone(result)
        self.assertEqual(prediction.status, "succeeded")
        self.assertEqual(prediction.output, "https://example.com/video.mp4")
        self.assertEqual([method for method, _ in self.client.predictions.requests], ["create", "get"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.output_video_size, "2k")
        self.assertEqual(record.output_video_duration_seconds, 10)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_video_wait_tracks_terminal_failure_without_deduction(self):
        self.client.predictions.responses.append(stubs.external.replicate_prediction(
            status = "failed", error = "provider failure",
        ))
        tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = VIDEO_GEN_P_VIDEO.id),
            purpose = ToolType.videos_gen,
            uses_credits = True,
        )
        decorator = self.di.replicate_client(tool, output_video_size = "2K", output_video_duration_seconds = 10)
        prediction = decorator.predictions.create(input = {"prompt": "test"})

        with self.assertRaises(ExternalServiceError) as raised:
            prediction.wait()

        self.assertEqual(raised.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertIn("status 'failed': provider failure", str(raised.exception))
        self.assertEqual([method for method, _ in self.client.predictions.requests], ["create"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_video_wait_cancels_and_tracks_timeout_without_deduction(self):
        self.client.predictions.responses.append(stubs.external.replicate_prediction(status = "processing"))
        tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = VIDEO_GEN_P_VIDEO.id),
            purpose = ToolType.videos_gen,
            uses_credits = True,
        )
        decorator = self.di.replicate_client(tool, output_video_size = "2K", output_video_duration_seconds = 10)
        prediction = decorator.predictions.create(input = {"prompt": "test"})

        # advance the system deadline without waiting ten minutes
        with patch("features.accounting.usage.decorators.replicate_usage_tracking_decorator.monotonic", side_effect = [0, 600]):
            with self.assertRaises(ExternalServiceError) as raised:
                prediction.wait()

        self.assertEqual(raised.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertIn("timed out", str(raised.exception))
        self.assertEqual(prediction.status, "canceled")
        self.assertEqual([method for method, _ in self.client.predictions.requests], ["create", "cancel"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)
