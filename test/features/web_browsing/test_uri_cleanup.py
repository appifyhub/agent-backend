import unittest

from features.web_browsing.uri_cleanup import simplify_url


class URICleanupTest(unittest.TestCase):

    def test_basic_url(self):
        url = "https://example.com"
        self.assertEqual(simplify_url(url), "example.com")

    def test_url_with_www(self):
        url = "https://www.example.com"
        self.assertEqual(simplify_url(url), "example.com")

    def test_url_with_path(self):
        url = "https://example.com/path/to/page"
        self.assertEqual(simplify_url(url), "example.com/path/to/page")

    def test_url_with_tracking_params(self):
        url = "https://example.com?utm_source=test&valid_param=value"
        self.assertEqual(simplify_url(url), "example.com?valid_param=value")

    def test_url_with_only_tracking_params(self):
        url = "https://example.com?utm_source=test&utm_medium=email"
        self.assertEqual(simplify_url(url), "example.com")

    def test_url_with_multiple_subdomains(self):
        url = "https://www.subdomain.example.com"
        self.assertEqual(simplify_url(url), "subdomain.example.com")

    def test_url_with_port(self):
        url = "https://example.com:8080/path"
        self.assertEqual(simplify_url(url), "example.com:8080/path")

    def test_url_with_fragment(self):
        url = "https://example.com/path#fragment"
        self.assertEqual(simplify_url(url), "example.com/path")

    def test_keep_subdomains_preserves_scheme_and_host(self):
        url = "https://www.example.com/path"
        self.assertEqual(simplify_url(url, strip_subdomains = False), "https://www.example.com/path")

    def test_keep_subdomains_still_strips_tracking_params(self):
        url = "https://www.example.com/page?utm_source=google&valid=1"
        self.assertEqual(simplify_url(url, strip_subdomains = False), "https://www.example.com/page?valid=1")

    def test_keep_subdomains_removes_all_tracking_params(self):
        url = "https://www.example.com?utm_source=x&utm_medium=y"
        self.assertEqual(simplify_url(url, strip_subdomains = False), "https://www.example.com")
