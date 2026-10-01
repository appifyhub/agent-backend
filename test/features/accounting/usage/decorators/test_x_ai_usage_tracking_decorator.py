from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_x_ai_client import FakeXAIClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.x_ai_usage_tracking_decorator import XAIUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GROK_4_3, IMAGE_GEN_GROK_IMAGINE
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class XAIUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    client: FakeXAIClient
    decorator: XAIUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = IMAGE_GEN_GROK_IMAGINE.id),
            purpose = ToolType.images_gen,
            uses_credits = True,
        )
        self.client = cast(FakeXAIClient, self.di.base_x_ai_client(self.tool))
        self.decorator = self.di.x_ai_client(self.tool, output_image_sizes = ["1k"])
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_sample_tracks_usage_by_image_size_and_deducts_credits(self):
        response = stubs.external.x_ai_image_response()
        self.client.image.responses.append(response)

        result = self.decorator.image.sample(prompt = "test prompt", model = self.tool.definition.id, image_format = "url")

        self.assertEqual(result.url, response.url)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, ToolType.images_gen)
        self.assertEqual(record.output_image_sizes, ["1k"])
        self.assertIsNone(record.input_tokens)
        self.assertIsNone(record.output_tokens)
        self.assertEqual(record.model_cost_credits, 0.5)
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_chat_sample_tracks_provider_reported_cost(self):
        response = stubs.external.x_ai_chat_response()
        self.client.chat.responses.append(response)
        tool = stubs.domain.configured_tool(definition = GROK_4_3, purpose = ToolType.search, uses_credits = True)
        decorator = self.di.x_ai_client(tool)

        result = decorator.chat.create(model = tool.definition.id).sample()

        self.assertEqual(result.id, response.id)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, tool.definition.id)
        self.assertEqual(record.model_cost_credits, 0.25)
        self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (10, 20, 30))
        self.assertEqual(record.total_cost_credits, 1.25)
        self.assertAlmostEqual(self.di.user_repo.get(self.user.id).credit_balance, self.user.credit_balance - 1.25)

    def test_chat_sample_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))
        conversation = self.decorator.chat.create(model = GROK_4_3.id)

        with self.assertRaises(ValidationError) as raised:
            conversation.sample()

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.chat.conversations[0].requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_chat_sample_provider_failure_tracks_without_deduction(self):
        error = ExternalServiceError("API error", UNEXPECTED_ERROR)
        self.client.chat.responses.append(error)

        with self.assertRaises(ExternalServiceError) as raised:
            self.decorator.chat.create(model = GROK_4_3.id).sample()

        self.assertIs(raised.exception, error)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_sample_measures_runtime(self):
        self.client.image.responses.append(stubs.external.x_ai_image_response())
        # control only the system clock to make elapsed time deterministic
        with patch("features.accounting.usage.decorators.x_ai_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            self.decorator.image.sample(prompt = "test", model = self.tool.definition.id)

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_sample_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))

        with self.assertRaises(ValidationError) as raised:
            self.decorator.image.sample(prompt = "test", model = self.tool.definition.id)

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.image.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_sample_failure_tracks_without_deduction(self):
        error = ExternalServiceError("API error", UNEXPECTED_ERROR)
        self.client.image.responses.append(error)

        with self.assertRaises(ExternalServiceError) as raised:
            self.decorator.image.sample(prompt = "test", model = self.tool.definition.id)

        self.assertIs(raised.exception, error)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_sample_passes_arguments_correctly(self):
        self.client.image.responses.append(stubs.external.x_ai_image_response())

        self.decorator.image.sample(
            prompt = "a robot", model = "grok-imagine-image", aspect_ratio = "16:9", resolution = "2k", image_format = "base64",
        )

        self.assertEqual(self.client.image.requests, [{
            "prompt": "a robot",
            "model": "grok-imagine-image",
            "aspect_ratio": "16:9",
            "resolution": "2k",
            "image_format": "base64",
        }])

    def test_no_output_image_sizes(self):
        self.client.image.responses.append(stubs.external.x_ai_image_response())
        decorator = self.di.x_ai_client(self.tool)

        decorator.image.sample(prompt = "test", model = self.tool.definition.id)

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertIsNone(record.output_image_sizes)
        self.assertEqual(record.model_cost_credits, 0)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )
