from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from requests.exceptions import HTTPError
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.http_usage_tracking_decorator import HTTPUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import X_READ_POST
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS
from util.errors import ValidationError


class HTTPUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    http: FakeHTTPClient
    decorator: HTTPUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = X_READ_POST.id),
            purpose = ToolType.api_twitter,
            uses_credits = True,
        )
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.decorator = self.di.tracked_http_get(self.tool)
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0
        # this legacy adapter calls the third-party requests transport directly
        self.enterContext(patch("requests.get", new = self.http.get))

    def test_get_tracks_api_call_and_deducts_credits(self):
        response = stubs.external.http_json_response({"data": "test"})
        self.http.responses["https://example.com"].append(response)

        result = self.decorator.get("https://example.com", headers = {"X-API-Key": "test"})

        self.assertEqual(result.json(), {"data": "test"})
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, self.tool.purpose)
        self.assertEqual(record.payer_id, self.user.id)
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertGreaterEqual(record.runtime_seconds, 0)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_get_measures_runtime(self):
        self.http.responses["https://example.com"].append(stubs.external.http_response())
        # the system clock is controlled to measure elapsed time without sleeping
        with patch("features.accounting.usage.decorators.http_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            self.decorator.get("https://example.com")

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_get_passes_kwargs_correctly(self):
        self.http.responses["https://example.com"].append(stubs.external.http_response())

        self.decorator.get("https://example.com", headers = {"X-API-Key": "test"}, params = {"id": "123"}, timeout = 30)

        self.assertEqual(self.http.requests, [("https://example.com", {
            "headers": {"X-API-Key": "test"}, "params": {"id": "123"}, "timeout": 30,
        })])

    def test_get_failure_tracks_without_deduction(self):
        error = HTTPError("404")
        self.http.responses["https://example.com"].append(error)

        with self.assertRaises(HTTPError) as raised:
            self.decorator.get("https://example.com")

        self.assertIs(raised.exception, error)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_get_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))

        with self.assertRaises(ValidationError) as raised:
            self.decorator.get("https://example.com")

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)
