from datetime import timedelta
from typing import cast
from unittest import TestCase

from fakes.fake_http_client import FakeHTTPClient
from requests.exceptions import Timeout
from stubs import external
from util.di_utils import di_for_tests

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from util.config import config

_URL = "https://example.com/main/VERSION"


class CliVersionServiceTest(TestCase):

    di: DI
    http: FakeHTTPClient

    def setUp(self):
        self.addCleanup(setattr, config, "cli_version_url", config.cli_version_url)
        config.cli_version_url = _URL
        self.di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, self.di.http_client())

    def test_blank_source_disables_discovery(self):
        config.cli_version_url = "  "

        self.assertIsNone(self.di.cli_version_service.get_version())
        self.assertEqual(self.http.requests, [])

    def test_normalizes_semver_and_caches_without_renewing_expiry(self):
        self.http.responses[_URL].append(external.http_response(content = b" v1.2.3-rc.1+build.7\n"))
        service = self.di.cli_version_service
        key = ToolsCache.create_key("cli-version", _URL)

        self.assertEqual(service.get_version(), "1.2.3-rc.1+build.7")
        cached = self.di.tools_cache_repo.get(key)
        self.assertEqual(cached.expires_at - cached.created_at, timedelta(hours = 1))
        self.assertEqual(service.get_version(), "1.2.3-rc.1+build.7")
        self.assertEqual(self.di.tools_cache_repo.get(key).expires_at, cached.expires_at)
        self.assertEqual([url for url, _ in self.http.requests], [_URL])

    def test_failed_lookups_do_not_prevent_later_success(self):
        self.http.responses[_URL].extend((
            external.http_response(content = b"1.2.3-rc.01"),
            external.http_response(content = b"1.2.3" + b" " * 1024),
            external.http_response(status_code = 404, content = b"1.2.3"),
            Timeout(),
            external.http_response(content = b"1.2.3\n"),
        ))
        service = self.di.cli_version_service
        key = ToolsCache.create_key("cli-version", _URL)

        for failure in ("invalid semver", "oversized", "404", "timeout"):
            with self.subTest(failure = failure):
                self.assertIsNone(service.get_version())
                self.assertIsNone(self.di.tools_cache_repo.get(key))

        self.assertEqual(service.get_version(), "1.2.3")

    def test_expired_version_is_not_served_when_refresh_fails(self):
        self.http.responses[_URL].extend((
            external.http_response(content = b"1.2.3"),
            Timeout(),
            external.http_response(content = b"1.2.4"),
        ))
        service = self.di.cli_version_service
        repo = self.di.tools_cache_repo
        key = ToolsCache.create_key("cli-version", _URL)
        self.assertEqual(service.get_version(), "1.2.3")
        cached = repo.get(key)
        cached.expires_at = cached.created_at - timedelta(hours = 1)
        repo.save(cached)

        self.assertIsNone(service.get_version())
        self.assertEqual(service.get_version(), "1.2.4")
