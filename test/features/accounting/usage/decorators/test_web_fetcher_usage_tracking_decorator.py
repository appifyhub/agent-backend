import unittest
from time import sleep
from unittest.mock import Mock
from uuid import UUID

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.web_fetcher_usage_tracking_decorator import WebFetcherUsageTrackingDecorator
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ToolType
from features.web_browsing.web_fetcher import WebFetcher


class WebFetcherUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_fetcher = Mock(spec = WebFetcher)
        self.mock_fetcher.made_request = True
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_api_call = Mock(return_value = Mock(spec = UsageRecord, total_cost_credits = 10.0))
        self.mock_spending_service = Mock(spec = SpendingService)
        self.tool_purpose = ToolType.api_fiat_exchange
        self.external_tool = Mock(spec = ExternalTool)
        self.external_tool.id = "test-tool"

        self.mock_configured_tool = Mock(spec = ConfiguredTool)
        self.mock_configured_tool.definition = self.external_tool
        self.mock_configured_tool.purpose = self.tool_purpose
        self.mock_configured_tool.payer_id = UUID(int = 1)
        self.mock_configured_tool.uses_credits = False

        self.decorator = WebFetcherUsageTrackingDecorator(
            wrapped_fetcher = self.mock_fetcher,
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = self.mock_configured_tool,
        )

    def test_fetch_json_tracks_usage(self):
        mock_response = {"data": "test"}
        self.mock_fetcher.fetch_json = Mock(return_value = mock_response)

        result = self.decorator.fetch_json()

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_api_call.assert_called_once()
        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertEqual(call_args.kwargs["tool"], self.external_tool)
        self.assertEqual(call_args.kwargs["tool_purpose"], self.tool_purpose)
        self.assertIsNotNone(call_args.kwargs["runtime_seconds"])
        self.assertGreater(call_args.kwargs["runtime_seconds"], 0)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_fetch_json_measures_runtime(self):
        def slow_fetch_json():
            sleep(0.01)
            return {"data": "test"}

        self.mock_fetcher.fetch_json = slow_fetch_json

        self.decorator.fetch_json()

        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_fetch_html_tracks_usage(self):
        mock_response = "<html>test</html>"
        self.mock_fetcher.fetch_html = Mock(return_value = mock_response)

        result = self.decorator.fetch_html()

        self.assertEqual(result, mock_response)
        self.mock_tracking_service.track_api_call.assert_called_once()

    def test_fetch_html_measures_runtime(self):
        def slow_fetch_html():
            sleep(0.01)
            return "<html>test</html>"

        self.mock_fetcher.fetch_html = slow_fetch_html

        self.decorator.fetch_html()

        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_delegates_url_property(self):
        self.mock_fetcher.url = "https://example.com"

        result = self.decorator.url

        self.assertEqual(result, "https://example.com")

    def test_delegates_json_property(self):
        self.mock_fetcher.json = {"key": "value"}

        result = self.decorator.json

        self.assertEqual(result, {"key": "value"})

    def test_delegates_html_property(self):
        self.mock_fetcher.html = "<html>content</html>"

        result = self.decorator.html

        self.assertEqual(result, "<html>content</html>")

    def test_delegates_request_metadata_properties(self):
        self.mock_fetcher.made_request = True
        self.mock_fetcher.status_code = 429
        self.mock_fetcher.error_json = {"status": "error", "code": 429}

        self.assertTrue(self.decorator.made_request)
        self.assertEqual(self.decorator.status_code, 429)
        self.assertEqual(self.decorator.error_json, {"status": "error", "code": 429})

    def test_fetch_json_calls_validate_pre_flight(self):
        self.mock_fetcher.fetch_json = Mock(return_value = {"data": "test"})

        self.decorator.fetch_json()

        self.mock_spending_service.validate_pre_flight.assert_called_once()

    def test_fetch_json_cache_hit_is_not_tracked_or_deducted(self):
        self.mock_fetcher.made_request = False
        self.mock_fetcher.fetch_json = Mock(return_value = {"data": "cached"})

        result = self.decorator.fetch_json()

        self.assertEqual(result, {"data": "cached"})
        self.mock_tracking_service.track_api_call.assert_not_called()
        self.mock_spending_service.deduct.assert_not_called()

    def test_fetch_html_cache_hit_is_not_tracked_or_deducted(self):
        self.mock_fetcher.made_request = False
        self.mock_fetcher.fetch_html = Mock(return_value = "<html>cached</html>")

        result = self.decorator.fetch_html()

        self.assertEqual(result, "<html>cached</html>")
        self.mock_tracking_service.track_api_call.assert_not_called()
        self.mock_spending_service.deduct.assert_not_called()

    def test_fetch_json_failure_tracks_without_deduction(self):
        self.mock_fetcher.fetch_json = Mock(side_effect = RuntimeError("Network error"))

        with self.assertRaises(RuntimeError):
            self.decorator.fetch_json()

        self.mock_tracking_service.track_api_call.assert_called_once()
        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()

    def test_fetch_html_failure_tracks_without_deduction(self):
        self.mock_fetcher.fetch_html = Mock(side_effect = RuntimeError("Network error"))

        with self.assertRaises(RuntimeError):
            self.decorator.fetch_html()

        self.mock_tracking_service.track_api_call.assert_called_once()
        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()
