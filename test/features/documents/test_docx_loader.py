from typing import cast
from unittest import TestCase

from fakes.http_client import FakeHTTPClient
from stubs import external
from util.di import di_for_tests

from features.documents.plain_text_loader import MAX_FILE_SIZE_BYTES
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util.error_codes import ATTACHMENT_PROCESSING_FAILED, DOCUMENT_SEARCH_FAILED
from util.errors import ExternalServiceError


class DocxLoaderTest(TestCase):

    URL = "http://test.com/file.docx"

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.loader = self.di.docx_loader(job_id = "job1", document_url = self.URL)

    def test_load_valid_docx_returns_single_document(self):
        content = "This is a paragraph."
        self.http.responses[self.URL].append(external.http_response(content = external.docx_document_bytes(content)))

        docs = self.loader.load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, content)
        self.assertEqual(docs[0].metadata["chunk"], 0)
        self.assertEqual(self.http.requests, [(self.URL, {"headers": DEFAULT_HEADERS})])

    def test_load_corrupt_docx_raises_document_search_failed(self):
        self.http.responses[self.URL].append(external.http_response(content = b"not a zip file"))

        with self.assertRaises(ExternalServiceError) as context:
            self.loader.load()

        self.assertEqual(context.exception.error_code, DOCUMENT_SEARCH_FAILED)

    def test_load_oversized_file_raises_attachment_processing_failed(self):
        self.http.responses[self.URL].append(external.http_response(content = b"x" * (MAX_FILE_SIZE_BYTES + 1)))

        with self.assertRaises(ExternalServiceError) as context:
            self.loader.load()

        self.assertEqual(context.exception.error_code, ATTACHMENT_PROCESSING_FAILED)
