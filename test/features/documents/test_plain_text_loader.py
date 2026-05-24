import unittest

import requests_mock

from features.documents.plain_text_loader import MAX_FILE_SIZE_BYTES, PlainTextLoader
from util.error_codes import ATTACHMENT_PROCESSING_FAILED, DOCUMENT_SEARCH_FAILED
from util.errors import ExternalServiceError


class PlainTextLoaderTest(unittest.TestCase):

    URL = "http://test.com/file.txt"

    @requests_mock.Mocker()
    def test_load_utf8_file_returns_single_document(self, m: requests_mock.Mocker):
        content = "Hello, world!"
        m.get(self.URL, content = content.encode("utf-8"), status_code = 200)

        docs = PlainTextLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, content)
        self.assertEqual(docs[0].metadata["chunk"], 0)

    @requests_mock.Mocker()
    def test_load_latin1_file_falls_back_to_replace(self, m: requests_mock.Mocker):
        latin1_bytes = "Héllo Wörld".encode("latin-1")
        m.get(self.URL, content = latin1_bytes, status_code = 200)

        docs = PlainTextLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(len(docs), 1)
        # Content should exist (replacement chars used); must not raise
        self.assertIsNotNone(docs[0].page_content)

    @requests_mock.Mocker()
    def test_load_empty_file_returns_empty_document(self, m: requests_mock.Mocker):
        m.get(self.URL, content = b"", status_code = 200)

        docs = PlainTextLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "")

    @requests_mock.Mocker()
    def test_load_oversized_file_raises_attachment_processing_failed(self, m: requests_mock.Mocker):
        oversized = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        m.get(self.URL, content = oversized, status_code = 200)

        with self.assertRaises(ExternalServiceError) as context:
            PlainTextLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(context.exception.error_code, ATTACHMENT_PROCESSING_FAILED)

    @requests_mock.Mocker()
    def test_load_request_failure_raises_document_search_failed(self, m: requests_mock.Mocker):
        m.get(self.URL, exc = ConnectionError("network failure"))

        with self.assertRaises(ExternalServiceError) as context:
            PlainTextLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(context.exception.error_code, DOCUMENT_SEARCH_FAILED)
