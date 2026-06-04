import unittest
from unittest.mock import Mock

from di.di import DI
from features.web_browsing.search_source_formatter import (
    format_sources_from_google,
    format_sources_from_perplexity,
)
from util.errors import ExternalServiceError


class SearchSourceFormatterTest(unittest.TestCase):

    def _make_di(self, short_url_side_effect=None):
        di = Mock(spec = DI)
        shortener = Mock()
        if short_url_side_effect:
            shortener.execute.side_effect = short_url_side_effect
        else:
            shortener.execute.return_value = "https://short.ly/abc"
        di.url_shortener.return_value = shortener
        return di

    def test_perplexity_sources_from_search_results(self):
        di = self._make_di()
        result_obj = Mock()
        result_obj.url = "https://www.formula1.com/race-results?utm_source=test"
        additional_kwargs = {"search_results": [result_obj]}

        output = format_sources_from_perplexity(additional_kwargs, di)

        self.assertIn("Sources:", output)
        self.assertIn("formula1.com", output)
        self.assertIn("https://short.ly/abc", output)

    def test_perplexity_sources_fall_back_to_citations(self):
        di = self._make_di()
        additional_kwargs = {
            "search_results": [],
            "citations": ["https://example.com/page"],
        }

        output = format_sources_from_perplexity(additional_kwargs, di)

        self.assertIn("Sources:", output)
        self.assertIn("https://short.ly/abc", output)

    def test_perplexity_tracking_params_stripped_before_shortening(self):
        di = self._make_di()
        result_obj = Mock()
        result_obj.url = "https://www.example.com/page?utm_source=google&valid=1"
        additional_kwargs = {"search_results": [result_obj]}

        format_sources_from_perplexity(additional_kwargs, di)

        called_url = di.url_shortener.call_args[0][0]
        self.assertTrue(called_url.startswith("https://"))
        self.assertNotIn("utm_source", called_url)
        self.assertIn("valid=1", called_url)

    def test_perplexity_duplicate_urls_deduped(self):
        di = self._make_di()
        r1 = Mock()
        r1.url = "https://example.com"
        r2 = Mock()
        r2.url = "https://example.com"
        additional_kwargs = {"search_results": [r1, r2]}

        format_sources_from_perplexity(additional_kwargs, di)

        self.assertEqual(di.url_shortener.call_count, 1)

    def test_shortener_failure_falls_back_to_raw_url(self):
        di = self._make_di(short_url_side_effect = ExternalServiceError("fail", "ERR"))
        result_obj = Mock()
        result_obj.url = "https://example.com/page"
        additional_kwargs = {"search_results": [result_obj]}

        output = format_sources_from_perplexity(additional_kwargs, di)

        self.assertIn("Sources:", output)
        self.assertIn("example.com", output)

    def test_perplexity_empty_additional_kwargs_returns_empty(self):
        di = self._make_di()
        output = format_sources_from_perplexity({}, di)
        self.assertEqual(output, "")

    def test_google_sources_from_grounding_chunks(self):
        di = self._make_di()
        chunk = Mock()
        chunk.web = Mock()
        chunk.web.title = "formula1.com"
        chunk.web.uri = "https://vertexaisearch.cloud.google.com/redirect/abc"

        output = format_sources_from_google([chunk], di)

        self.assertIn("Sources:", output)
        self.assertIn("formula1.com", output)
        self.assertIn("https://short.ly/abc", output)

    def test_google_sources_deduped(self):
        di = self._make_di()
        uri = "https://vertexaisearch.cloud.google.com/redirect/abc"
        chunks = []
        for _ in range(3):
            c = Mock()
            c.web = Mock()
            c.web.title = "example.com"
            c.web.uri = uri
            chunks.append(c)

        format_sources_from_google(chunks, di)

        self.assertEqual(di.url_shortener.call_count, 1)

    def test_google_uri_passed_unmodified_to_shortener(self):
        di = self._make_di()
        redirect_uri = "https://vertexaisearch.cloud.google.com/redirect/token123==/"
        chunk = Mock()
        chunk.web = Mock()
        chunk.web.title = "example.com"
        chunk.web.uri = redirect_uri

        format_sources_from_google([chunk], di)

        called_url = di.url_shortener.call_args[0][0]
        self.assertEqual(called_url, redirect_uri)

    def test_google_empty_chunks_returns_empty(self):
        di = self._make_di()
        output = format_sources_from_google([], di)
        self.assertEqual(output, "")
