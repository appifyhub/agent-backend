from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_http_client import FakeHTTPClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.web_fetcher_usage_tracking_decorator import WebFetcherUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import FIAT_CURRENCY_EXCHANGE
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class WebFetcherUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    http: FakeHTTPClient
    decorator: WebFetcherUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = FIAT_CURRENCY_EXCHANGE.id),
            purpose = ToolType.api_fiat_exchange,
            uses_credits = True,
        )
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.decorator = self.di.tracked_web_fetcher(self.tool, "https://example.com")
        for name, value in (("usage_maintenance_fee_credits", 1.0), ("web_retries", 1), ("web_retry_delay_s", 0)):
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)

    def test_fetch_json_tracks_usage_and_deducts_credits(self):
        self.http.responses[self.decorator.url].append(stubs.external.http_json_response({"data": "test"}))

        result = self.decorator.fetch_json()

        self.assertEqual(result, {"data": "test"})
        self.assertEqual(self.decorator.json, result)
        self.assertTrue(self.decorator.made_request)
        self.assertEqual(self.decorator.status_code, 200)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, self.tool.purpose)
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_fetch_html_tracks_usage_and_deducts_credits(self):
        self.http.responses[self.decorator.url].append(stubs.external.http_response(content = b"<html>test</html>"))

        result = self.decorator.fetch_html()

        self.assertEqual(result, "<html>test</html>")
        self.assertEqual(self.decorator.html, result)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_fetch_measures_runtime(self):
        for method in ("fetch_json", "fetch_html"):
            with self.subTest(method = method):
                url = f"https://example.com/{method}"
                self.http.responses[url].append(stubs.external.http_json_response({"data": "test"}))
                decorator = self.di.tracked_web_fetcher(self.tool, url)
                # the system clock makes runtime deterministic without replacing fetch behavior
                with patch(
                    "features.accounting.usage.decorators.web_fetcher_usage_tracking_decorator.time",
                    side_effect = [10, 10.25],
                ):
                    getattr(decorator, method)()
                record = self.di.usage_record_repo.get_by_user(self.user.id)[0]
                self.assertEqual(record.runtime_seconds, 0.25)

    def test_delegates_url_property(self):
        self.assertEqual(self.decorator.url, "https://example.com")

    def test_delegates_request_metadata_properties(self):
        self.http.responses[self.decorator.url].append(stubs.external.http_json_response(
            {"status": "error", "code": 429}, status_code = 429,
        ))

        self.decorator.fetch_json()

        self.assertTrue(self.decorator.made_request)
        self.assertEqual(self.decorator.status_code, 429)
        self.assertEqual(self.decorator.error_json, {"status": "error", "code": 429})

    def test_fetch_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))
        for method in ("fetch_json", "fetch_html"):
            with self.subTest(method = method), self.assertRaises(ValidationError) as raised:
                getattr(self.decorator, method)()
            self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_fetch_json_cache_hit_is_not_tracked_or_deducted(self):
        self.http.responses[self.decorator.url].append(stubs.external.http_json_response({"data": "cached"}))
        self.di.web_fetcher(self.decorator.url).fetch_json()

        result = self.decorator.fetch_json()

        self.assertEqual(result, {"data": "cached"})
        self.assertFalse(self.decorator.made_request)
        self.assertEqual(len(self.http.requests), 1)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_fetch_html_cache_hit_is_not_tracked_or_deducted(self):
        self.http.responses[self.decorator.url].append(stubs.external.http_response(content = b"<html>cached</html>"))
        self.di.web_fetcher(self.decorator.url).fetch_html()

        result = self.decorator.fetch_html()

        self.assertEqual(result, "<html>cached</html>")
        self.assertFalse(self.decorator.made_request)
        self.assertEqual(len(self.http.requests), 1)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_fetch_failure_tracks_without_deduction(self):
        for method in ("fetch_json", "fetch_html"):
            with self.subTest(method = method):
                error = ExternalServiceError("Transport failed", UNEXPECTED_ERROR)
                self.http.responses[self.decorator.url].append(error)
                with self.assertRaises(ExternalServiceError) as raised:
                    getattr(self.decorator, method)()
                self.assertIs(raised.exception, error)
        records = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.is_failed for record in records))
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)
