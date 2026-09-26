from datetime import datetime, timedelta
from json import dumps
from typing import cast
from unittest import TestCase

from fakes.http_client import FakeHTTPClient
from requests.exceptions import Timeout
from stubs import domain, external
from util.di import di_for_tests

from features.tools_cache.tools_cache import ToolsCache
from features.web_browsing.twitter_status_fetcher import CACHE_PREFIX as TWEET_CACHE_PREFIX
from features.web_browsing.uri_cleanup import simplify_url
from features.web_browsing.web_fetcher import (
    CACHE_PREFIX,
    DEFAULT_CACHE_TTL_HTML,
    DEFAULT_CACHE_TTL_JSON,
    DEFAULT_HEADERS,
)
from util.config import config

DEFAULT_URL = "https://example.com"
TWEET_URL = "https://twitter.com/user/status/123456"


class WebFetcherTest(TestCase):

    def setUp(self):
        for name, value in {"web_retries": 1, "web_retry_delay_s": 0, "web_timeout_s": 1}.items():
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)
        user = domain.user()
        self.di = self.enterContext(di_for_tests(invoker_id = user.id.hex))
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.di.user_repo.save(user)
        self.cache_key = ToolsCache.create_key(
            CACHE_PREFIX,
            f"{simplify_url(DEFAULT_URL)}|{dumps(DEFAULT_HEADERS, sort_keys = True)}|{{}}",
        )

    def test_auto_fetch_html_disabled(self):
        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertIsNone(fetcher.html)
        self.assertFalse(fetcher.made_request)
        self.assertEqual(self.http.requests, [])

    def test_auto_fetch_html_enabled(self):
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"data"))

        fetcher = self.di.web_fetcher(DEFAULT_URL, auto_fetch_html = True)

        self.assertEqual(fetcher.html, "data")
        self.assertEqual(len(self.http.requests), 1)

    def test_fetch_html_ok_cache_hit(self):
        self.__seed_cache("Cached HTML content")
        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertEqual(fetcher.fetch_html(), "Cached HTML content")
        self.assertFalse(fetcher.made_request)
        self.assertEqual(self.http.requests, [])

    def test_fetch_html_force_bypasses_cache_and_replaces_it(self):
        self.__seed_cache("Old content")
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"Fresh HTML content"))
        fetcher = self.di.web_fetcher(DEFAULT_URL, force = True)

        self.assertEqual(fetcher.fetch_html(), "Fresh HTML content")
        self.assertTrue(fetcher.made_request)
        self.assertEqual(self.di.tools_cache_repo.get(self.cache_key).value, "Fresh HTML content")
        self.assertEqual(len(self.di.tools_cache_repo.get_all()), 1)
        self.assertEqual(len(self.http.requests), 1)

    def test_fetch_html_expired_cache_refreshes(self):
        self.__seed_cache("Expired content", expires_at = datetime.now() - timedelta(seconds = 1))
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"Fresh HTML content"))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_html(), "Fresh HTML content")
        cached = self.di.tools_cache_repo.get(self.cache_key)
        self.assertEqual(cached.value, "Fresh HTML content")
        self.assertFalse(cached.is_expired())

    def test_fetch_html_ok_cache_miss(self):
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"data"))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_html(), "data")
        self.assertEqual(self.di.tools_cache_repo.get(self.cache_key).value, "data")

    def test_fetch_html_error(self):
        self.http.responses[DEFAULT_URL].append(external.http_response(status_code = 404))

        fetcher = self.di.web_fetcher(DEFAULT_URL, auto_fetch_html = True)

        self.assertIsNone(fetcher.html)
        self.assertEqual(fetcher.status_code, 404)
        self.assertIsNone(self.di.tools_cache_repo.get(self.cache_key))

    def test_fetch_html_binary_content(self):
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"%PDF-1.4\x00binarydata"))

        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertIsNone(fetcher.fetch_html())
        self.assertIsNone(fetcher.html)
        self.assertIsNone(self.di.tools_cache_repo.get(self.cache_key))

    def test_auto_fetch_json_disabled(self):
        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertIsNone(fetcher.json)
        self.assertEqual(self.http.requests, [])

    def test_auto_fetch_json_enabled(self):
        self.http.responses[DEFAULT_URL].append(external.http_json_response({"value": "data"}))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL, auto_fetch_json = True).json, {"value": "data"})

    def test_fetch_json_ok_cache_miss(self):
        self.http.responses[DEFAULT_URL].append(external.http_json_response({"value": "data"}))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_json(), {"value": "data"})
        self.assertEqual(self.di.tools_cache_repo.get(self.cache_key).value, dumps({"value": "data"}))

    def test_fetch_json_ok_cache_hit(self):
        self.__seed_cache(dumps({"key": "Cached value"}))
        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertEqual(fetcher.fetch_json(), {"key": "Cached value"})
        self.assertFalse(fetcher.made_request)
        self.assertEqual(self.http.requests, [])

    def test_fetch_json_force_bypasses_cache_and_replaces_it(self):
        self.__seed_cache(dumps({"key": "Old value"}))
        self.http.responses[DEFAULT_URL].append(external.http_json_response({"key": "Fresh value"}))
        fetcher = self.di.web_fetcher(DEFAULT_URL, force = True)

        self.assertEqual(fetcher.fetch_json(), {"key": "Fresh value"})
        self.assertTrue(fetcher.made_request)
        self.assertEqual(self.di.tools_cache_repo.get(self.cache_key).value, dumps({"key": "Fresh value"}))
        self.assertEqual(len(self.di.tools_cache_repo.get_all()), 1)
        self.assertEqual(len(self.http.requests), 1)

    def test_fetch_json_expired_cache_refreshes(self):
        self.__seed_cache(dumps({"key": "Expired"}), expires_at = datetime.now() - timedelta(seconds = 1))
        self.http.responses[DEFAULT_URL].append(external.http_json_response({"key": "Fresh value"}))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_json(), {"key": "Fresh value"})
        cached = self.di.tools_cache_repo.get(self.cache_key)
        self.assertEqual(cached.value, dumps({"key": "Fresh value"}))
        self.assertFalse(cached.is_expired())

    def test_custom_cache_ttl_html(self):
        self.__assert_cache_ttl(timedelta(minutes = 10), as_json = False, custom = True)

    def test_custom_cache_ttl_json(self):
        self.__assert_cache_ttl(timedelta(minutes = 2), as_json = True, custom = True)

    def test_default_cache_ttl_html(self):
        self.__assert_cache_ttl(DEFAULT_CACHE_TTL_HTML, as_json = False, custom = False)

    def test_default_cache_ttl_json(self):
        self.__assert_cache_ttl(DEFAULT_CACHE_TTL_JSON, as_json = True, custom = False)

    def test_fetch_json_error(self):
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"", status_code = 404))

        fetcher = self.di.web_fetcher(DEFAULT_URL, auto_fetch_json = True)

        self.assertIsNone(fetcher.json)
        self.assertEqual(fetcher.status_code, 404)
        self.assertIsNone(self.di.tools_cache_repo.get(self.cache_key))

    def test_fetch_json_retains_structured_http_error(self):
        error = {"status": "error", "code": 429, "message": "API credits exhausted"}
        self.http.responses[DEFAULT_URL].append(external.http_json_response(error, status_code = 429))
        fetcher = self.di.web_fetcher(DEFAULT_URL)

        self.assertIsNone(fetcher.fetch_json())
        self.assertEqual(fetcher.status_code, 429)
        self.assertEqual(fetcher.error_json, error)
        self.assertIsNone(self.di.tools_cache_repo.get(self.cache_key))

    def test_custom_headers(self):
        custom_headers = {"X-Custom-Header": "test_value"}
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"data"))

        fetcher = self.di.web_fetcher(DEFAULT_URL, headers = custom_headers, auto_fetch_html = True)

        self.assertEqual(fetcher.html, "data")
        self.assertEqual(self.http.requests, [(
            DEFAULT_URL, {"headers": DEFAULT_HEADERS | custom_headers, "params": {}, "timeout": 1},
        )])

    def test_custom_params(self):
        params = {"param1": "value1", "param2": "value2"}
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"data"))

        fetcher = self.di.web_fetcher(DEFAULT_URL, params = params, auto_fetch_html = True)

        self.assertEqual(fetcher.html, "data")
        self.assertEqual(self.http.requests, [(DEFAULT_URL, {"headers": DEFAULT_HEADERS, "params": params, "timeout": 1})])

    def test_fetch_html_with_headers_and_params(self):
        headers = {"X-Custom-Header": "test_value"}
        params = {"param1": "value1", "param2": "value2"}
        self.http.responses[DEFAULT_URL].append(external.http_response(content = b"data"))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL, headers = headers, params = params).fetch_html(), "data")
        self.assertEqual(self.http.requests, [(
            DEFAULT_URL, {"headers": DEFAULT_HEADERS | headers, "params": params, "timeout": 1},
        )])

    def test_fetch_json_with_headers_and_params(self):
        headers = {"X-Custom-Header": "test_value"}
        params = {"param1": "value1", "param2": "value2"}
        self.http.responses[DEFAULT_URL].append(external.http_json_response({"value": "data"}))

        self.assertEqual(
            self.di.web_fetcher(DEFAULT_URL, headers = headers, params = params).fetch_json(),
            {"value": "data"},
        )
        self.assertEqual(self.http.requests, [(
            DEFAULT_URL, {"headers": DEFAULT_HEADERS | headers, "params": params, "timeout": 1},
        )])

    def test_fetch_html_twitter(self):
        self.__seed_tweet()

        result = self.di.web_fetcher(TWEET_URL).fetch_html()

        self.assertEqual(result, "<html><body>\n<p>\nTweet content\n</p>\n</body></html>")
        self.assertEqual(self.http.requests, [])

    def test_fetch_json_twitter(self):
        self.__seed_tweet()

        self.assertEqual(self.di.web_fetcher(TWEET_URL).fetch_json(), {"content": "Tweet content"})
        self.assertEqual(self.http.requests, [])

    def test_fetch_html_non_twitter(self):
        self.__seed_cache("Cached HTML content")

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_html(), "Cached HTML content")
        self.assertEqual(self.http.requests, [])

    def test_fetch_json_non_twitter(self):
        self.__seed_cache(dumps({"key": "Cached value"}))

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_json(), {"key": "Cached value"})
        self.assertEqual(self.http.requests, [])

    def test_shortened_tweet_url_uses_injected_http_client(self):
        self.__seed_tweet()
        short_url = "https://t.co/example"
        self.http.responses[short_url].append(external.http_response(url = TWEET_URL))

        self.assertEqual(self.di.web_fetcher(short_url).fetch_json(), {"content": "Tweet content"})
        self.assertEqual(self.http.requests, [(short_url, {"timeout": 1})])

    def test_fetch_html_retries_transport_failure_and_caches_success(self):
        config.web_retries = 2
        self.http.responses[DEFAULT_URL].extend([
            Timeout("first attempt failed"), external.http_response(content = b"recovered"),
        ])

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL).fetch_html(), "recovered")
        self.assertEqual(len(self.http.requests), 2)
        cached_fetcher = self.di.web_fetcher(DEFAULT_URL)
        self.assertEqual(cached_fetcher.fetch_html(), "recovered")
        self.assertFalse(cached_fetcher.made_request)
        self.assertEqual(len(self.http.requests), 2)

    def test_fetch_json_stops_after_configured_retries(self):
        config.web_retries = 2
        self.http.responses[DEFAULT_URL].extend([Timeout("first attempt"), Timeout("second attempt")])

        self.assertIsNone(self.di.web_fetcher(DEFAULT_URL).fetch_json())
        self.assertEqual(len(self.http.requests), 2)
        self.assertIsNone(self.di.tools_cache_repo.get(self.cache_key))

    def test_request_parameters_distinguish_cached_results(self):
        self.http.responses[DEFAULT_URL].extend([
            external.http_response(content = b"first page"),
            external.http_response(content = b"second page"),
        ])

        self.assertEqual(self.di.web_fetcher(DEFAULT_URL, params = {"page": 1}).fetch_html(), "first page")
        self.assertEqual(self.di.web_fetcher(DEFAULT_URL, params = {"page": 2}).fetch_html(), "second page")
        self.assertEqual(self.di.web_fetcher(DEFAULT_URL, params = {"page": 1}).fetch_html(), "first page")
        self.assertEqual(len(self.http.requests), 2)
        self.assertEqual(len(self.di.tools_cache_repo.get_all()), 2)

    def __seed_cache(self, value: str, expires_at: datetime | None = None) -> None:
        self.di.tools_cache_repo.save(domain.tools_cache(key = self.cache_key, value = value, expires_at = expires_at))

    def __seed_tweet(self) -> None:
        self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(TWEET_CACHE_PREFIX, "123456"),
            value = "Tweet content",
        ))

    def __assert_cache_ttl(self, ttl: timedelta, as_json: bool, custom: bool) -> None:
        self.http.responses[DEFAULT_URL].append(
            external.http_json_response({"value": "data"}) if as_json else external.http_response(content = b"data"),
        )
        fetcher = self.di.web_fetcher(
            DEFAULT_URL,
            cache_ttl_json = ttl if custom and as_json else None,
            cache_ttl_html = ttl if custom and not as_json else None,
        )
        before = datetime.now()
        fetcher.fetch_json() if as_json else fetcher.fetch_html()
        after = datetime.now()

        cached = self.di.tools_cache_repo.get(self.cache_key)
        self.assertIsNotNone(cached)
        self.assertIsNotNone(cached.expires_at)
        self.assertGreaterEqual(cached.expires_at, before + ttl)
        self.assertLessEqual(cached.expires_at, after + ttl)
