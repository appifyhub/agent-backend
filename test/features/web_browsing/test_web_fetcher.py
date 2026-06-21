import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import requests_mock

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from features.web_browsing.web_fetcher import (
    DEFAULT_HEADERS,
    WebFetcher,
)
from util.config import config

DEFAULT_URL = "https://example.com"


class WebFetcherTest(unittest.TestCase):

    mock_di: DI
    cache_entry_html: ToolsCache
    cache_entry_json: ToolsCache

    def setUp(self):
        config.web_retries = 1
        config.web_retry_delay_s = 0
        config.web_timeout_s = 1

        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.tools_cache_repo = MagicMock(spec = ToolsCacheRepository)
        # noinspection PyPropertyAccess
        self.mock_di.tool_choice_resolver = MagicMock()
        self.mock_di.twitter_status_fetcher = MagicMock()

        self.cache_entry_html = ToolsCache(
            key = "web-fetcher::test_key",
            value = "Cached HTML content",
            expires_at = datetime.now() + timedelta(hours = 1),
        )
        self.cache_entry_json = ToolsCache(
            key = "web-fetcher::test_key",
            value = json.dumps({"key": "Cached value"}),
            expires_at = datetime.now() + timedelta(hours = 1),
        )

    @requests_mock.Mocker()
    def test_auto_fetch_html_disabled(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        self.assertIsNone(fetcher.html)

    @requests_mock.Mocker()
    def test_auto_fetch_html_enabled(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            auto_fetch_html = True,
        )
        self.assertEqual(fetcher.html, "data")

    def test_fetch_html_ok_cache_hit(self):
        self.mock_di.tools_cache_repo.get.return_value = self.cache_entry_html
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_html()
        self.assertEqual(result, "Cached HTML content")

    @requests_mock.Mocker()
    def test_fetch_html_expired_cache_refreshes(self, m: requests_mock.Mocker):
        expired = ToolsCache(
            key = "expired",
            value = "Expired HTML content",
            expires_at = datetime.now() - timedelta(seconds = 1),
        )
        self.mock_di.tools_cache_repo.get.return_value = expired
        m.get(DEFAULT_URL, text = "Fresh HTML content", status_code = 200)

        fetcher = WebFetcher(DEFAULT_URL, self.mock_di)
        result = fetcher.fetch_html()

        self.assertEqual(result, "Fresh HTML content")
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_fetch_html_ok_cache_miss(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_html()
        self.assertEqual(result, "data")

    @requests_mock.Mocker()
    def test_fetch_html_error(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, status_code = 404)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            auto_fetch_html = True,
        )
        self.assertIsNone(fetcher.html)

    @requests_mock.Mocker()
    def test_fetch_html_binary_content(self, m: requests_mock.Mocker):
        # Simulate binary PDF response with NUL bytes
        binary_content = b"%PDF-1.4\x00binarydata"
        m.get(DEFAULT_URL, content = binary_content, status_code = 200, headers = {"Content-Type": "application/pdf"})
        self.mock_di.tools_cache_repo.get.return_value = None

        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_html()
        self.assertIsNone(result)
        self.assertIsNone(fetcher.html)

    @requests_mock.Mocker()
    def test_auto_fetch_json_disabled(self, m: requests_mock.Mocker):
        stub = {"value": "data"}
        m.get(DEFAULT_URL, json = stub, status_code = 200)
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        self.assertIsNone(fetcher.json)

    @requests_mock.Mocker()
    def test_auto_fetch_json_enabled(self, m: requests_mock.Mocker):
        stub = {"value": "data"}
        m.get(DEFAULT_URL, json = stub, status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            auto_fetch_json = True,
        )
        self.assertEqual(fetcher.json, stub)

    @requests_mock.Mocker()
    def test_fetch_json_ok_cache_miss(self, m: requests_mock.Mocker):
        stub = {"value": "data"}
        m.get(DEFAULT_URL, json = stub, status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_json()
        self.assertEqual(result, stub)

    def test_fetch_json_ok_cache_hit(self):
        self.mock_di.tools_cache_repo.get.return_value = self.cache_entry_json
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_json()
        self.assertEqual(result, {"key": "Cached value"})

    @requests_mock.Mocker()
    def test_fetch_json_expired_cache_refreshes(self, m: requests_mock.Mocker):
        expired = ToolsCache(
            key = "expired",
            value = json.dumps({"key": "Expired value"}),
            expires_at = datetime.now() - timedelta(seconds = 1),
        )
        self.mock_di.tools_cache_repo.get.return_value = expired
        m.get(DEFAULT_URL, json = {"key": "Fresh value"}, status_code = 200)

        fetcher = WebFetcher(DEFAULT_URL, self.mock_di)
        result = fetcher.fetch_json()

        self.assertEqual(result, {"key": "Fresh value"})
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_custom_cache_ttl_html(self, m: requests_mock.Mocker):
        custom_ttl = timedelta(minutes = 10)
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            cache_ttl_html = custom_ttl,
        )
        fetcher.fetch_html()
        # Verify that save was called with the custom TTL
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_custom_cache_ttl_json(self, m: requests_mock.Mocker):
        custom_ttl = timedelta(minutes = 2)
        m.get(DEFAULT_URL, json = {"value": "data"}, status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            cache_ttl_json = custom_ttl,
        )
        fetcher.fetch_json()
        # Verify that save was called with the custom TTL
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_default_cache_ttl_html(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        fetcher.fetch_html()
        # Verify that save was called
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_default_cache_ttl_json(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, json = {"value": "data"}, status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        fetcher.fetch_json()
        # Verify that save was called
        # noinspection PyUnresolvedReferences
        self.mock_di.tools_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_fetch_json_error(self, m: requests_mock.Mocker):
        m.get(DEFAULT_URL, status_code = 404)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            auto_fetch_json = True,
        )
        self.assertIsNone(fetcher.json)

    @requests_mock.Mocker()
    def test_custom_headers(self, m: requests_mock.Mocker):
        custom_headers = {"X-Custom-Header": "test_value"}
        expected_headers = {**DEFAULT_HEADERS, **custom_headers}
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            headers = custom_headers,
            auto_fetch_html = True,
        )
        # Access the html property to use the fetcher variable
        self.assertEqual(fetcher.html, "data")
        # Verify the request was made with the expected headers
        self.assertEqual(len(m.request_history), 1)
        for key, value in expected_headers.items():
            self.assertEqual(m.request_history[0].headers[key], value)

    @requests_mock.Mocker()
    def test_custom_params(self, m: requests_mock.Mocker):
        custom_params = {"param1": "value1", "param2": "value2"}
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            params = custom_params,
            auto_fetch_html = True,
        )
        # Access the html property to use the fetcher variable
        self.assertEqual(fetcher.html, "data")
        # Verify the request was made with the expected parameters
        self.assertEqual(len(m.request_history), 1)
        self.assertIn("param1=value1", m.request_history[0].url)
        self.assertIn("param2=value2", m.request_history[0].url)

    @requests_mock.Mocker()
    def test_fetch_html_with_headers_and_params(self, m: requests_mock.Mocker):
        custom_headers = {"X-Custom-Header": "test_value"}
        custom_params = {"param1": "value1", "param2": "value2"}
        m.get(DEFAULT_URL, text = "data", status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            headers = custom_headers,
            params = custom_params,
        )
        result = fetcher.fetch_html()
        self.assertEqual(result, "data")

    @requests_mock.Mocker()
    def test_fetch_json_with_headers_and_params(self, m: requests_mock.Mocker):
        custom_headers = {"X-Custom-Header": "test_value"}
        custom_params = {"param1": "value1", "param2": "value2"}
        stub = {"value": "data"}
        m.get(DEFAULT_URL, json = stub, status_code = 200)
        self.mock_di.tools_cache_repo.get.return_value = None
        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
            headers = custom_headers,
            params = custom_params,
        )
        result = fetcher.fetch_json()
        self.assertEqual(result, stub)

    @patch("features.web_browsing.web_fetcher.resolve_tweet_id")
    def test_fetch_html_twitter(self, mock_resolve_tweet_id):
        mock_resolve_tweet_id.return_value = "123456"

        # Mock the twitter_status_fetcher method and its return value
        mock_twitter_fetcher = Mock()
        mock_twitter_fetcher.execute.return_value = "Tweet content"
        self.mock_di.twitter_status_fetcher.return_value = mock_twitter_fetcher

        # Test cache miss scenario
        self.mock_di.tools_cache_repo.get.return_value = None

        fetcher = WebFetcher(
            "https://twitter.com/user/status/123456",
            self.mock_di,
        )
        result = fetcher.fetch_html()

        # Verify twitter_status_fetcher was called with correct parameters
        # noinspection PyUnresolvedReferences
        self.mock_di.twitter_status_fetcher.assert_called_once()
        self.assertIsNotNone(result)
        self.assertIn("Tweet content", str(result))

    @patch("features.web_browsing.web_fetcher.resolve_tweet_id")
    def test_fetch_json_twitter(self, mock_resolve_tweet_id):
        mock_resolve_tweet_id.return_value = "123456"

        # Mock the twitter_status_fetcher method and its return value
        mock_twitter_fetcher = Mock()
        mock_twitter_fetcher.execute.return_value = "Tweet content"
        self.mock_di.twitter_status_fetcher.return_value = mock_twitter_fetcher

        # Test cache miss scenario
        self.mock_di.tools_cache_repo.get.return_value = None

        fetcher = WebFetcher(
            "https://twitter.com/user/status/123456",
            self.mock_di,
        )
        result = fetcher.fetch_json()

        # Verify twitter_status_fetcher was called with correct parameters
        # noinspection PyUnresolvedReferences
        self.mock_di.twitter_status_fetcher.assert_called_once()
        self.assertEqual(result, {"content": "Tweet content"})

    @patch("features.web_browsing.web_fetcher.resolve_tweet_id")
    def test_fetch_html_non_twitter(self, mock_resolve_tweet_id):
        mock_resolve_tweet_id.return_value = None

        mock_cache_entry = ToolsCache(
            key = "test_cache_key",
            value = "Cached HTML content",
            expires_at = datetime.now() + timedelta(hours = 1),
        )
        self.mock_di.tools_cache_repo.get.return_value = mock_cache_entry

        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_html()
        self.assertEqual(result, "Cached HTML content")

    @patch("features.web_browsing.web_fetcher.resolve_tweet_id")
    def test_fetch_json_non_twitter(self, mock_resolve_tweet_id):
        mock_resolve_tweet_id.return_value = None

        mock_cache_entry = ToolsCache(
            key = "test_cache_key",
            value = json.dumps({"key": "Cached value"}),
            expires_at = datetime.now() + timedelta(hours = 1),
        )
        self.mock_di.tools_cache_repo.get.return_value = mock_cache_entry

        fetcher = WebFetcher(
            DEFAULT_URL,
            self.mock_di,
        )
        result = fetcher.fetch_json()
        self.assertEqual(result, {"key": "Cached value"})
