import io
import unittest

import requests_mock
from docx import Document as DocxDocument

from features.documents.docx_loader import DocxLoader
from features.documents.plain_text_loader import MAX_FILE_SIZE_BYTES
from util.error_codes import ATTACHMENT_PROCESSING_FAILED, DOCUMENT_SEARCH_FAILED
from util.errors import ExternalServiceError


def _make_docx_bytes(text: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class DocxLoaderTest(unittest.TestCase):

    URL = "http://test.com/file.docx"

    @requests_mock.Mocker()
    def test_load_valid_docx_returns_single_document(self, m: requests_mock.Mocker):
        content = "This is a paragraph."
        m.get(self.URL, content = _make_docx_bytes(content), status_code = 200)

        docs = DocxLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(len(docs), 1)
        self.assertIn(content, docs[0].page_content)
        self.assertEqual(docs[0].metadata["chunk"], 0)

    @requests_mock.Mocker()
    def test_load_corrupt_docx_raises_document_search_failed(self, m: requests_mock.Mocker):
        m.get(self.URL, content = b"not a zip file", status_code = 200)

        with self.assertRaises(ExternalServiceError) as context:
            DocxLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(context.exception.error_code, DOCUMENT_SEARCH_FAILED)

    @requests_mock.Mocker()
    def test_load_oversized_file_raises_attachment_processing_failed(self, m: requests_mock.Mocker):
        m.get(self.URL, content = b"x" * (MAX_FILE_SIZE_BYTES + 1), status_code = 200)

        with self.assertRaises(ExternalServiceError) as context:
            DocxLoader(job_id = "job1", document_url = self.URL).load()

        self.assertEqual(context.exception.error_code, ATTACHMENT_PROCESSING_FAILED)
