import unittest
from uuid import UUID

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.message.formatted_chat_message import (
    ATTACHMENT_PLACEHOLDER_REGEX,
    FormattedAttachmentPart,
    FormattedAttachmentReference,
    FormattedChatMessage,
    FormattedQuotePart,
    FormattedTextPart,
)
from util.functions import generate_deterministic_short_uuid


class FormattedChatMessageTest(unittest.TestCase):

    def test_to_text_joins_non_empty_parts(self):
        message = FormattedChatMessage(parts = [
            FormattedTextPart(text = "First"),
            FormattedTextPart(text = None),
            FormattedTextPart(text = "Second"),
        ])

        result = message.to_text()

        self.assertEqual(result, "First\n\nSecond")

    def test_attachment_reference_from_attachment(self):
        attachment = ChatAttachment(
            id = "local123",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 2),
            mime_type = "image/png",
        )

        result = FormattedAttachmentReference.from_attachment(attachment)

        self.assertEqual(result.to_text(), "local123 (image/png)")

    def test_attachment_reference_from_remote_data(self):
        attachment = ChatAttachmentRemoteData(
            external_id = "remote123",
            message_id = "m1",
            mime_type = "image/jpeg",
        )

        result = FormattedAttachmentReference.from_remote_data(attachment)

        self.assertEqual(result.to_text(), f"{generate_deterministic_short_uuid('remote123')} (image/jpeg)")

    def test_attachment_part_formats_multiple_attachments(self):
        result = FormattedAttachmentPart(attachments = [
            FormattedAttachmentReference(id = "a1", mime_type = "image/png"),
            FormattedAttachmentReference(id = "a2"),
        ]).to_text()

        self.assertEqual(result, "📎 [ a1 (image/png), a2 ]")

    def test_attachment_placeholder_regex_matches_formatted_part(self):
        text = "📎 [ a1 (image/png), a2 ]"

        result = ATTACHMENT_PLACEHOLDER_REGEX.fullmatch(text)

        self.assertIsNotNone(result)

    def test_quote_part_formats_quote_depth(self):
        quote = FormattedQuotePart(
            message = FormattedChatMessage(parts = [FormattedTextPart(text = "Quoted")]),
        )

        result = quote.to_text()

        self.assertEqual(result, ">> Quoted")

    def test_from_text_replaces_existing_attachment_marker(self):
        attachment = ChatAttachment(
            id = "local123",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 2),
            mime_type = "image/png",
        )

        result = FormattedChatMessage.from_text(
            "Caption\n\n📎 [ remote123 ]",
            [attachment],
        )

        self.assertEqual(result.to_text(), "Caption\n\n📎 [ local123 (image/png) ]")

    def test_with_attachments_replaces_existing_attachment_part(self):
        old_attachment = ChatAttachment(
            id = "old123",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 2),
        )
        new_attachment = ChatAttachment(
            id = "new123",
            chat_id = UUID(int = 1),
            uploader_user_id = UUID(int = 2),
        )
        message = FormattedChatMessage(parts = [
            FormattedTextPart(text = "Caption"),
            FormattedAttachmentPart.from_attachments([old_attachment]),
        ])

        result = message.with_attachments([new_attachment])

        self.assertEqual(result.to_text(), "Caption\n\n📎 [ new123 ]")

    def test_prepend_quote_prefixes_all_lines(self):
        message = FormattedChatMessage(parts = [
            FormattedTextPart(text = "Current"),
        ])
        quote = FormattedChatMessage(parts = [
            FormattedTextPart(text = "Line one\nLine two"),
            FormattedAttachmentPart(attachments = [FormattedAttachmentReference(id = "local123")]),
        ])

        result = message.prepend_quote(quote)

        self.assertEqual(result.to_text(), ">>>> Line one\n>>>> Line two\n\n>>>> 📎 [ local123 ]\n\nCurrent")
