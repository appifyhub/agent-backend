import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.chat_attachment_utils import resolve_all_attachments, resolve_local_attachments
from util.errors import NotFoundError, ValidationError


class ValidateSourcesTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = MagicMock()
        self.mock_di.platform_bot_sdk = MagicMock(return_value = MagicMock())
        mock_resolver = MagicMock()
        mock_resolver.execute.return_value = MagicMock()
        self.mock_di.url_attachment_resolver.return_value = mock_resolver

    def test_both_empty_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            resolve_all_attachments([], [], self.mock_di)
        self.assertIn("No attachment IDs provided", str(ctx.exception))

    def test_both_none_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            resolve_all_attachments(None, None, self.mock_di)
        self.assertIn("No attachment IDs provided", str(ctx.exception))


class FetchAttachmentsTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = MagicMock()
        self.attachment = ChatMessageAttachment(
            id = "att1",
            external_id = "ext1",
            chat_id = UUID(int = 1),
            message_id = "msg1",
            size = 1024,
            last_url = "http://test.com/image.png",
            last_url_until = int((datetime.now() + timedelta(hours = 1)).timestamp()),
            extension = "png",
            mime_type = "image/png",
        )
        self.mock_di.chat_message_attachment_repo.get.return_value = self.attachment
        self.mock_di.platform_bot_sdk.return_value.refresh_attachment_instances.side_effect = lambda x: x

    def test_empty_ids_returns_empty(self):
        result = resolve_local_attachments([], self.mock_di)
        self.assertEqual(result, [])
        self.mock_di.chat_message_attachment_repo.get.assert_not_called()

    def test_valid_id_returns_attachment(self):
        result = resolve_local_attachments(["att1"], self.mock_di)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "att1")
        self.assertIsInstance(result[0], ChatMessageAttachment)

    def test_empty_string_id_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            resolve_local_attachments([""], self.mock_di)
        self.assertIn("Attachment ID cannot be empty", str(ctx.exception))

    def test_not_found_raises(self):
        self.mock_di.chat_message_attachment_repo.get.return_value = None
        with self.assertRaises(NotFoundError) as ctx:
            resolve_local_attachments(["missing"], self.mock_di)
        self.assertIn("not found in DB", str(ctx.exception))

    def test_multiple_ids_fetches_all(self):
        result = resolve_local_attachments(["att1", "att1"], self.mock_di)
        self.assertEqual(len(result), 2)


class ResolveAllAttachmentsTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = MagicMock()
        self.attachment = ChatMessageAttachment(
            id = "att1",
            external_id = "ext1",
            chat_id = UUID(int = 1),
            message_id = "msg1",
            size = 1024,
            last_url = "http://test.com/image.png",
            last_url_until = int((datetime.now() + timedelta(hours = 1)).timestamp()),
            extension = "png",
            mime_type = "image/png",
        )
        self.mock_di.chat_message_attachment_repo.get.return_value = self.attachment

        self.mock_platform_sdk = MagicMock()
        self.mock_di.platform_bot_sdk = MagicMock(return_value = self.mock_platform_sdk)
        self.mock_platform_sdk.refresh_attachment_instances.return_value = [self.attachment]

        self.url_attachment = ChatMessageAttachment(
            id = "url-abc123",
            chat_id = UUID(int = 1),
            message_id = "virtual",
            mime_type = "image/png",
            extension = "png",
            last_url = "http://example.com/photo.png",
            last_url_until = int((datetime.now() + timedelta(hours = 1)).timestamp()),
        )
        mock_resolver = MagicMock()
        mock_resolver.execute.return_value = self.url_attachment
        self.mock_di.url_attachment_resolver.return_value = mock_resolver

    def test_both_empty_raises(self):
        with self.assertRaises(ValidationError):
            resolve_all_attachments([], [], self.mock_di)

    def test_ids_only(self):
        result = resolve_all_attachments(["att1"], [], self.mock_di)
        self.assertEqual(result, [self.attachment])
        self.mock_platform_sdk.refresh_attachment_instances.assert_called_once()
        self.mock_di.url_attachment_resolver.assert_not_called()

    def test_urls_only(self):
        self.mock_platform_sdk.refresh_attachment_instances.return_value = []
        result = resolve_all_attachments([], ["http://example.com/photo.png"], self.mock_di)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.url_attachment)

    def test_ids_and_urls_merged(self):
        result = resolve_all_attachments(["att1"], ["http://example.com/photo.png"], self.mock_di)
        self.assertEqual(len(result), 2)
        self.assertIn(self.attachment, result)
        self.assertIn(self.url_attachment, result)

    def test_refresh_called_with_empty_when_no_ids(self):
        self.mock_platform_sdk.refresh_attachment_instances.return_value = []
        resolve_all_attachments([], ["http://example.com/photo.png"], self.mock_di)
        self.mock_platform_sdk.refresh_attachment_instances.assert_called_once_with([])
