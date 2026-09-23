import unittest
from time import sleep
from unittest.mock import Mock

import requests
import stubs

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.decorators.http_usage_tracking_decorator import HTTPUsageTrackingDecorator
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.external_tool import ToolType


class HTTPUsageTrackingDecoratorTest(unittest.TestCase):

    def setUp(self):
        self.mock_tracking_service = Mock(spec = UsageTrackingService)
        self.mock_tracking_service.track_api_call = Mock(
            return_value = stubs.domain.usage_record(total_cost_credits = 10.0),
        )
        self.mock_spending_service = Mock(spec = SpendingService)
        configured_tool = stubs.domain.configured_tool(
            purpose = ToolType.api_twitter,
        )

        self.decorator = HTTPUsageTrackingDecorator(
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

    def test_get_tracks_api_call(self):
        mock_response = Mock(spec = requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.api_twitter)
        decorator = HTTPUsageTrackingDecorator(
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

        with unittest.mock.patch("requests.get", return_value = mock_response) as mock_get:
            result = decorator.get(
                "https://api.example.com/test",
                headers = {"X-API-Key": "test"},
            )

        self.assertEqual(result, mock_response)
        mock_get.assert_called_once_with("https://api.example.com/test", headers = {"X-API-Key": "test"})
        self.mock_tracking_service.track_api_call.assert_called_once()
        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertIs(call_args.kwargs["tool"], configured_tool.definition)
        self.assertEqual(call_args.kwargs["tool_purpose"], ToolType.api_twitter)
        self.assertIsNotNone(call_args.kwargs["runtime_seconds"])
        self.assertGreater(call_args.kwargs["runtime_seconds"], 0)
        self.assertEqual(call_args.kwargs["uses_credits"], False)

    def test_get_measures_runtime(self):
        mock_response = Mock(spec = requests.Response)

        def slow_get(*args, **kwargs):
            sleep(0.01)
            return mock_response

        with unittest.mock.patch("requests.get", side_effect = slow_get):
            self.decorator.get("https://api.example.com/test")

        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertGreaterEqual(call_args.kwargs["runtime_seconds"], 0.01)

    def test_get_passes_kwargs_correctly(self):
        mock_response = Mock(spec = requests.Response)

        with unittest.mock.patch("requests.get", return_value = mock_response) as mock_get:
            self.decorator.get(
                "https://api.example.com/test",
                headers = {"X-API-Key": "test"},
                params = {"id": "123"},
                timeout = 30,
            )

        mock_get.assert_called_once_with(
            "https://api.example.com/test",
            headers = {"X-API-Key": "test"},
            params = {"id": "123"},
            timeout = 30,
        )

    def test_get_failure_tracks_without_deduction(self):
        with unittest.mock.patch("requests.get", side_effect = requests.exceptions.HTTPError("404")):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.decorator.get("https://api.example.com/test")

        self.mock_tracking_service.track_api_call.assert_called_once()
        call_args = self.mock_tracking_service.track_api_call.call_args
        self.assertTrue(call_args.kwargs["is_failed"])
        self.mock_spending_service.deduct.assert_not_called()

    def test_get_calls_validate_pre_flight(self):
        mock_response = Mock(spec = requests.Response)
        configured_tool = stubs.domain.configured_tool(purpose = ToolType.api_twitter)
        decorator = HTTPUsageTrackingDecorator(
            tracking_service = self.mock_tracking_service,
            spending_service = self.mock_spending_service,
            configured_tool = configured_tool,
        )

        with unittest.mock.patch("requests.get", return_value = mock_response):
            decorator.get("https://api.example.com/test")

        self.mock_spending_service.validate_pre_flight.assert_called_once_with(configured_tool)
