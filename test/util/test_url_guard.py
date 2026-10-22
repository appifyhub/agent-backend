from typing import cast
from unittest import TestCase

from fakes.fake_http_client import FakeHTTPClient
from stubs import external
from util.di_utils import di_for_tests

from di.di import DI
from util.error_codes import WEB_FETCH_FAILED
from util.errors import ValidationError
from util.url_guard import guarded_get, validate_public_http_url

PUBLIC_URL = "https://example.com/page"
METADATA_URL = "http://169.254.169.254/latest/meta-data/"


class UrlGuardTest(TestCase):

    di: DI
    http: FakeHTTPClient

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, self.di.http_client())

    def test_refuses_destinations_outside_the_public_internet(self):
        refused = {
            "non-http scheme": "file:///etc/passwd",
            "opaque scheme": "gopher://example.com/",
            "missing host": "http:///no-host",
            "loopback literal": "http://127.0.0.1:8080/admin",
            "loopback name": "http://localhost/admin",
            "ipv6 loopback": "http://[::1]/admin",
            "cloud metadata": METADATA_URL,
            "private range": "http://10.0.0.5/internal",
            "private range alt": "http://192.168.1.1/router",
        }

        for label, url in refused.items():
            with self.subTest(label = label):
                with self.assertRaises(ValidationError) as context:
                    validate_public_http_url(url)
                self.assertEqual(context.exception.error_code, WEB_FETCH_FAILED)

    def test_allows_public_destination(self):
        self.assertEqual(validate_public_http_url(PUBLIC_URL), PUBLIC_URL)

    def test_guarded_get_refuses_redirect_into_internal_address(self):
        self.http.responses[PUBLIC_URL].append(external.http_response(
            status_code = 302,
            headers = {"Location": METADATA_URL},
        ))

        with self.assertRaises(ValidationError) as context:
            guarded_get(self.http, PUBLIC_URL)

        self.assertEqual(context.exception.error_code, WEB_FETCH_FAILED)
        self.assertEqual([url for url, _ in self.http.requests], [PUBLIC_URL])

    def test_guarded_get_follows_redirect_to_public_address(self):
        final_url = "https://example.com/final"
        self.http.responses[PUBLIC_URL].append(external.http_response(
            status_code = 302,
            headers = {"Location": final_url},
        ))
        self.http.responses[final_url].append(external.http_response(content = b"arrived"))

        response = guarded_get(self.http, PUBLIC_URL)

        self.assertEqual(response.content, b"arrived")
        self.assertEqual([url for url, _ in self.http.requests], [PUBLIC_URL, final_url])
