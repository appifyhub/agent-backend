from typing import cast
from unittest import TestCase

from fakes.http_client import FakeHTTPClient
from requests.exceptions import ConnectionError
from stubs import external
from util.di import di_for_tests

from features.documents.plain_text_loader import MAX_FILE_SIZE_BYTES
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util.error_codes import ATTACHMENT_PROCESSING_FAILED, DOCUMENT_SEARCH_FAILED
from util.errors import ExternalServiceError


class PlainTextLoaderTest(TestCase):

    URL = "http://test.com/file.txt"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.loader = self.di.plain_text_loader(job_id = "job1", document_url = self.URL)

    def test_load_utf8_file_returns_single_document(self):
        content = "Hello, world!"
        self.http.responses[self.URL].append(external.http_response(content = content.encode("utf-8")))

        docs = self.loader.load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, content)
        self.assertEqual(docs[0].metadata["chunk"], 0)
        self.assertEqual(self.http.requests, [(self.URL, {"headers": DEFAULT_HEADERS})])

    def test_load_latin1_file_falls_back_to_replace(self):
        self.http.responses[self.URL].append(external.http_response(content = "Héllo Wörld".encode("latin-1")))

        docs = self.loader.load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "H�llo W�rld")

    def test_load_empty_file_returns_empty_document(self):
        self.http.responses[self.URL].append(external.http_response(content = b""))

        docs = self.loader.load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "")

    def test_load_oversized_file_raises_attachment_processing_failed(self):
        self.http.responses[self.URL].append(external.http_response(content = b"x" * (MAX_FILE_SIZE_BYTES + 1)))

        with self.assertRaises(ExternalServiceError) as context:
            self.loader.load()

        self.assertEqual(context.exception.error_code, ATTACHMENT_PROCESSING_FAILED)

    def test_load_request_failure_raises_document_search_failed(self):
        failure = ConnectionError("network failure")
        self.http.responses[self.URL].append(failure)

        with self.assertRaises(ExternalServiceError) as context:
            self.loader.load()

        self.assertEqual(context.exception.error_code, DOCUMENT_SEARCH_FAILED)
        self.assertIs(context.exception.__cause__, failure)
