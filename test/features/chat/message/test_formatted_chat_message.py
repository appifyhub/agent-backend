import unittest

import stubs

from features.chat.message.formatted_chat_message import (
    ATTACHMENT_PLACEHOLDER_REGEX,
    FormattedAttachmentPart,
    FormattedAttachmentReference,
    FormattedChatMessage,
)


class FormattedChatMessageTest(unittest.TestCase):

    def test_to_text_joins_non_empty_parts(self):
        message = stubs.domain.formatted_chat_message(
            parts = [
                stubs.domain.formatted_text_part(text = "First"),
                stubs.domain.formatted_text_part(text = None),
                stubs.domain.formatted_text_part(text = "Second"),
            ],
        )

        result = message.to_text()

        self.assertEqual(result, "First\n\nSecond")

    def test_attachment_reference_from_attachment(self):
        attachment = stubs.domain.chat_attachment(
            id = "local123",
            mime_type = "image/png",
        )

        result = FormattedAttachmentReference.from_attachment(attachment)

        self.assertEqual(result.to_text(), "local123 (image/png)")

    def test_attachment_part_formats_multiple_attachments(self):
        result = stubs.domain.formatted_attachment_part(
            attachments = [
                stubs.domain.formatted_attachment_reference(id = "a1", mime_type = "image/png"),
                stubs.domain.formatted_attachment_reference(id = "a2", mime_type = None),
            ],
        ).to_text()

        self.assertEqual(result, "📎 [ a1 (image/png), a2 ]")

    def test_attachment_placeholder_regex_matches_formatted_part(self):
        text = "📎 [ a1 (image/png), a2 ]"

        result = ATTACHMENT_PLACEHOLDER_REGEX.fullmatch(text)

        self.assertIsNotNone(result)

    def test_quote_part_formats_quote_depth(self):
        quote = stubs.domain.formatted_quote_part(
            message = stubs.domain.formatted_chat_message(parts = [stubs.domain.formatted_text_part(text = "Quoted")]),
        )

        result = quote.to_text()

        self.assertEqual(result, ">> Quoted")

    def test_from_text_replaces_existing_attachment_marker(self):
        attachment = stubs.domain.chat_attachment(
            id = "local123",
            mime_type = "image/png",
        )

        result = FormattedChatMessage.from_text(
            "Caption\n\n📎 [ remote123 ]",
            [attachment],
        )

        self.assertEqual(result.to_text(), "Caption\n\n📎 [ local123 (image/png) ]")

    def test_with_attachments_replaces_existing_attachment_part(self):
        old_attachment = stubs.domain.chat_attachment(
            id = "old123",
            mime_type = None,
        )
        new_attachment = stubs.domain.chat_attachment(
            id = "new123",
            mime_type = None,
        )
        message = stubs.domain.formatted_chat_message(
            parts = [
                stubs.domain.formatted_text_part(text = "Caption"),
                FormattedAttachmentPart.from_attachments([old_attachment]),
            ],
        )

        result = message.with_attachments([new_attachment])

        self.assertEqual(result.to_text(), "Caption\n\n📎 [ new123 ]")

    def test_prepend_quote_prefixes_all_lines(self):
        message = stubs.domain.formatted_chat_message(
            parts = [
                stubs.domain.formatted_text_part(text = "Current"),
            ],
        )
        quote = stubs.domain.formatted_chat_message(
            parts = [
                stubs.domain.formatted_text_part(text = "Line one\nLine two"),
                stubs.domain.formatted_attachment_part(
                    attachments = [stubs.domain.formatted_attachment_reference(id = "local123", mime_type = None)],
                ),
            ],
        )

        result = message.prepend_quote(quote)

        self.assertEqual(result.to_text(), ">>>> Line one\n>>>> Line two\n\n>>>> 📎 [ local123 ]\n\nCurrent")

    def test_prepend_quote_uses_explicit_depth(self):
        message = stubs.domain.formatted_chat_message(parts = [stubs.domain.formatted_text_part(text = "Current")])
        quote = stubs.domain.formatted_chat_message(parts = [stubs.domain.formatted_text_part(text = "Selected quote")])

        result = message.prepend_quote(quote, depth = 1)

        self.assertEqual(result.to_text(), ">> Selected quote\n\nCurrent")
