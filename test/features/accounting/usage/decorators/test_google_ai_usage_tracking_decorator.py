from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_google_ai_client import FakeGoogleAIClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.google_ai_usage_tracking_decorator import GoogleAIUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import NANO_BANANA
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class GoogleAIUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    client: FakeGoogleAIClient
    decorator: GoogleAIUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = NANO_BANANA.id),
            purpose = ToolType.images_gen,
            uses_credits = True,
        )
        self.client = cast(FakeGoogleAIClient, self.di.base_google_ai_client(self.tool.token.get_secret_value()))
        self.decorator = self.di.google_ai_client(self.tool, output_image_sizes = ["1k"], input_image_sizes = ["2k"])
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_generate_content_measures_runtime(self):
        self.client.models.responses.append(stubs.external.google_generate_content_response())
        # control only the system clock to make elapsed time deterministic
        with patch("features.accounting.usage.decorators.google_ai_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            self.decorator.models.generate_content(model = self.tool.definition.id, contents = "test prompt")

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_other_models_methods_pass_through_without_tracking(self):
        model = stubs.external.google_model()
        self.client.models.catalog[model.name] = model

        self.assertEqual(self.decorator.models.get(model = model.name), model)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_client_attributes_pass_through(self):
        self.assertFalse(self.decorator.vertexai)

    def test_decorator_passes_arguments_correctly(self):
        self.client.models.responses.append(stubs.external.google_generate_content_response())

        self.decorator.models.generate_content(
            model = "test-model", contents = "test prompt", config = {"temperature": 0.7},
        )

        self.assertEqual(self.client.models.requests, [{
            "model": "test-model", "contents": "test prompt", "config": {"temperature": 0.7},
        }])

    def test_generate_content_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))

        with self.assertRaises(ValidationError) as raised:
            self.decorator.models.generate_content(model = self.tool.definition.id, contents = "test prompt")

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.models.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_generate_content_failure_tracks_without_deduction(self):
        error = ExternalServiceError("API error", UNEXPECTED_ERROR)
        self.client.models.responses.append(error)

        with self.assertRaises(ExternalServiceError) as raised:
            self.decorator.models.generate_content(model = self.tool.definition.id, contents = "test prompt")

        self.assertIs(raised.exception, error)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_generate_content_tracks_usage_and_deducts_credits(self):
        response = stubs.external.google_generate_content_response()
        self.client.models.responses.append(response)

        result = self.decorator.models.generate_content(model = self.tool.definition.id, contents = "test prompt")

        self.assertEqual(result, response)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, ToolType.images_gen)
        self.assertEqual(record.output_image_sizes, ["1k"])
        self.assertEqual(record.input_image_sizes, ["2k"])
        self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (100, 200, 300))
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_generate_content_with_no_usage_metadata(self):
        self.client.models.responses.append(stubs.external.google_generate_content_response(usage_metadata = None))

        self.decorator.models.generate_content(model = self.tool.definition.id, contents = "test prompt")

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertIsNone(record.input_tokens)
        self.assertIsNone(record.output_tokens)
        self.assertIsNone(record.total_tokens)
        self.assertEqual(record.output_image_sizes, ["1k"])
        self.assertEqual(record.input_image_sizes, ["2k"])
        self.assertEqual(record.model_cost_credits, 0.7)
