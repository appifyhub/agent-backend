from typing import cast
from unittest import TestCase

from fakes.fake_http_client import FakeHTTPClient
from stubs import external
from util.di_utils import di_for_tests

from features.web_browsing.twitter_utils import resolve_tweet_id
from util.config import config


class TwitterUtilsTest(TestCase):

    http: FakeHTTPClient

    def setUp(self):
        di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, di.http_client())

    def test_detect_tweet_id(self):
        self.http.responses["https://t.co/abcdefg"].append(external.http_response(
            url = "https://twitter.com/username/status/123456789",
        ))
        test_cases = [
            ("https://twitter.com/username/status/123456789", "123456789"),
            ("https://x.com/username/status/123456789", "123456789"),
            ("https://twitter.com/username/status/123456789?s=20", "123456789"),
            ("https://t.co/abcdefg", "123456789"),
            ("https://example.com", None),
        ]
        for url, expected_id in test_cases:
            with self.subTest(url = url):
                self.assertEqual(resolve_tweet_id(url, http_client = self.http), expected_id)

        self.assertEqual(self.http.requests, [("https://t.co/abcdefg", {"timeout": config.web_timeout_s})])
