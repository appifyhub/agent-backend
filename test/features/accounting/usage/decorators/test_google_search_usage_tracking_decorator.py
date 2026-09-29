from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_google_ai_client import FakeGoogleAIClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.google_search_usage_tracking_decorator import GoogleSearchUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GEMINI_FLASH_LATEST
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class GoogleSearchUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    client: FakeGoogleAIClient
    decorator: GoogleSearchUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = GEMINI_FLASH_LATEST.id),
            purpose = ToolType.search,
            uses_credits = True,
        )
        self.client = cast(FakeGoogleAIClient, self.di.base_google_ai_client(self.tool.token.get_secret_value()))
        self.decorator = self.di.google_search_client(self.tool)
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_generate_content_measures_runtime(self):
        self.client.models.responses.append(stubs.external.google_generate_content_response())
        # control only the system clock to make elapsed time deterministic
        with patch("features.accounting.usage.decorators.google_search_usage_tracking_decorator.time", side_effect = [10, 10.25]):
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

    def test_generate_content_tracks_tokens_and_query_costs(self):
        response = stubs.external.google_grounding_response(query_count = 3)
        self.client.models.responses.append(response)

        result = self.decorator.models.generate_content(model = self.tool.definition.id, contents = "query")

        self.assertEqual(result, response)
        records = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(len(records), 4)
        token_record, = [record for record in records if record.total_tokens is not None]
        self.assertEqual((token_record.input_tokens, token_record.output_tokens, token_record.total_tokens), (10, 250, 260))
        self.assertEqual(token_record.tool.id, self.tool.definition.id)
        self.assertEqual(token_record.tool_purpose, ToolType.search)
        self.assertTrue(token_record.uses_credits)
        self.assertFalse(token_record.is_failed)
        query_records = [record for record in records if record.total_tokens is None]
        for record in query_records:
            self.assertEqual(record.total_cost_credits, self.tool.definition.cost_estimate.web_search_query)
            self.assertEqual(record.maintenance_fee_credits, 0)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - sum(record.total_cost_credits for record in records),
        )

    def test_generate_content_skips_query_records_when_zero_queries(self):
        self.client.models.responses.append(stubs.external.google_grounding_response(query_count = 0))

        self.decorator.models.generate_content(model = self.tool.definition.id, contents = "query")

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.total_tokens, 260)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_generate_content_with_no_usage_metadata(self):
        self.client.models.responses.append(stubs.external.google_grounding_response(usage_metadata = None))

        self.decorator.models.generate_content(model = self.tool.definition.id, contents = "query")

        records = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(len(records), 3)
        token_record, = [record for record in records if record.maintenance_fee_credits > 0]
        self.assertIsNone(token_record.input_tokens)
        self.assertIsNone(token_record.output_tokens)
        self.assertIsNone(token_record.total_tokens)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - sum(record.total_cost_credits for record in records),
        )
