from typing import cast
from unittest import TestCase

from fakes.fake_url_shortener import FakeUrlShortener
from stubs import external
from util.di_utils import di_for_tests

from di.di import DI
from features.web_browsing.search_source_formatter import (
    format_sources_from_google,
    format_sources_from_perplexity,
    format_sources_from_xai,
)
from util.error_codes import URL_SHORTENER_FAILED
from util.errors import ExternalServiceError


class SearchSourceFormatterTest(TestCase):

    di: DI
    shortener: FakeUrlShortener

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.shortener = cast(FakeUrlShortener, self.di.url_shortener("https://example.com/page"))
        self.shortener.short_url = "https://short.ly/abc"

    def test_perplexity_sources_from_search_results(self):
        response = external.ai_message(additional_kwargs = {
            "search_results": [external.perplexity_search_result(
                url = "https://www.formula1.com/race-results?utm_source=test",
            )],
        })

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "\n\nSources:\n- [www.formula1.com](https://short.ly/abc)")

    def test_perplexity_sources_fall_back_to_citations(self):
        response = external.ai_message(additional_kwargs = {
            "search_results": [],
            "citations": ["https://example.com/page"],
        })

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "\n\nSources:\n- [example.com](https://short.ly/abc)")

    def test_perplexity_tracking_params_stripped_on_shortener_failure(self):
        self.shortener.error = ExternalServiceError("Shortening failed", URL_SHORTENER_FAILED)
        response = external.ai_message(additional_kwargs = {
            "search_results": [external.perplexity_search_result(
                url = "https://www.example.com/page?utm_source=google&valid=1",
            )],
        })

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "\n\nSources:\n- [www.example.com](https://www.example.com/page?valid=1)")

    def test_perplexity_duplicate_urls_deduped(self):
        response = external.ai_message(additional_kwargs = {
            "search_results": [external.perplexity_search_result(), external.perplexity_search_result()],
        })

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "\n\nSources:\n- [example.com](https://short.ly/abc)")
        self.assertEqual(self.shortener.executions, 1)

    def test_shortener_failure_falls_back_to_raw_url(self):
        self.shortener.error = ExternalServiceError("Shortening failed", URL_SHORTENER_FAILED)
        response = external.ai_message(additional_kwargs = {
            "search_results": [external.perplexity_search_result()],
        })

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "\n\nSources:\n- [example.com](https://example.com/page)")

    def test_perplexity_empty_additional_kwargs_returns_empty(self):
        response = external.ai_message()

        output = format_sources_from_perplexity(response.additional_kwargs, self.di)

        self.assertEqual(output, "")
        self.assertEqual(self.shortener.executions, 0)

    def test_google_sources_from_grounding_chunks(self):
        chunk = external.google_grounding_chunk(web = {
            "title": "formula1.com",
            "uri": "https://vertexaisearch.cloud.google.com/redirect/abc",
        })

        output = format_sources_from_google([chunk], self.di)

        self.assertEqual(output, "\n\nSources:\n- [formula1.com](https://short.ly/abc)")

    def test_google_sources_deduped(self):
        chunks = [external.google_grounding_chunk() for _ in range(3)]

        output = format_sources_from_google(chunks, self.di)

        self.assertEqual(output, "\n\nSources:\n- [example.com](https://short.ly/abc)")
        self.assertEqual(self.shortener.executions, 1)

    def test_google_redirect_uri_preserved_on_shortener_failure(self):
        self.shortener.error = ExternalServiceError("Shortening failed", URL_SHORTENER_FAILED)
        redirect_uri = "https://vertexaisearch.cloud.google.com/redirect/token123==/"
        chunk = external.google_grounding_chunk(web = {"title": "example.com", "uri": redirect_uri})

        output = format_sources_from_google([chunk], self.di)

        self.assertEqual(output, f"\n\nSources:\n- [example.com]({redirect_uri})")

    def test_google_empty_chunks_returns_empty(self):
        output = format_sources_from_google([], self.di)

        self.assertEqual(output, "")
        self.assertEqual(self.shortener.executions, 0)

    def test_xai_sources_from_citations(self):
        response = external.x_ai_chat_response(citations = ["https://example.com/page"])

        output = format_sources_from_xai(response, self.di)

        self.assertEqual(output, "\n\nSources:\n- [example.com](https://short.ly/abc)")

    def test_xai_empty_sources_returns_empty(self):
        response = external.x_ai_chat_response()

        output = format_sources_from_xai(response, self.di)

        self.assertEqual(output, "")
        self.assertEqual(self.shortener.executions, 0)
