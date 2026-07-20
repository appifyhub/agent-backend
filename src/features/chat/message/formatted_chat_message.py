from __future__ import annotations

import re
from dataclasses import dataclass, field

from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from util.functions import generate_deterministic_short_uuid as uuid_of

ATTACHMENT_PLACEHOLDER_TEXT = "📎 [ {attachments} ]"
ATTACHMENT_PLACEHOLDER_REGEX = re.compile(r"📎 \[ [^\]\r\n]+ \]")


@dataclass(kw_only = True)
class FormattedAttachmentReference:
    """A reference to one attachment in a formatted message.

    Example::

        a1 (image/png)
    """

    id: str
    mime_type: str | None = None

    @classmethod
    def from_attachment(cls, attachment: ChatAttachment) -> FormattedAttachmentReference:
        return cls(id = attachment.id, mime_type = attachment.mime_type)

    @classmethod
    def from_remote_data(cls, attachment: ChatAttachmentRemoteData) -> FormattedAttachmentReference:
        return cls(id = uuid_of(attachment.external_id), mime_type = attachment.mime_type)

    def to_text(self) -> str:
        return f"{self.id} ({self.mime_type})" if self.mime_type else self.id


@dataclass(kw_only = True)
class FormattedTextPart:
    """A plain-text part of a formatted message.

    Example::

        Hello
    """

    text: str | None

    def to_text(self) -> str:
        return self.text or ""


@dataclass(kw_only = True)
class FormattedAttachmentPart:
    """The attachment placeholder part of a formatted message.

    Example::

        📎 [ a1 (image/png) ]
    """

    attachments: list[FormattedAttachmentReference]

    @classmethod
    def from_attachments(cls, attachments: list[ChatAttachment]) -> FormattedAttachmentPart:
        return cls(
            attachments = [
                FormattedAttachmentReference.from_attachment(attachment)
                for attachment in attachments
            ],
        )

    @classmethod
    def from_remote_data(cls, attachments: list[ChatAttachmentRemoteData]) -> FormattedAttachmentPart:
        return cls(
            attachments = [
                FormattedAttachmentReference.from_remote_data(attachment)
                for attachment in attachments
            ],
        )

    def to_text(self) -> str:
        if not self.attachments:
            return ""
        attachments = ", ".join(attachment.to_text() for attachment in self.attachments)
        return ATTACHMENT_PLACEHOLDER_TEXT.format(attachments = attachments)


@dataclass(kw_only = True)
class FormattedQuotePart:
    """A quoted message part, with its nesting depth reflected in the prefix.

    Example::

        >> Earlier message
    """

    message: FormattedChatMessage
    depth: int = 1

    def to_text(self) -> str:
        text = self.message.to_text()
        if not text:
            return ""
        prefix = ">>" * self.depth
        paragraphs = [
            "\n".join(f"{prefix} {line}" for line in paragraph.split("\n"))
            for paragraph in text.split("\n\n")
        ]
        return "\n\n".join(paragraphs)


type FormattedChatMessagePart = FormattedTextPart | FormattedAttachmentPart | FormattedQuotePart


@dataclass(kw_only = True)
class FormattedChatMessage:
    """A message assembled from structured text, attachment, and quote parts.

    Example::

        Photo caption

        📎 [ a1 (image/png) ]
    """

    parts: list[FormattedChatMessagePart] = field(default_factory = list)

    @classmethod
    def from_text(
        cls,
        text: str,
        attachments: list[ChatAttachment] | None = None,
    ) -> FormattedChatMessage:
        text_parts = [
            part
            for part in text.split("\n\n")
            if not ATTACHMENT_PLACEHOLDER_REGEX.fullmatch(part)
        ]
        parts: list[FormattedChatMessagePart] = [
            FormattedTextPart(text = "\n\n".join(text_parts)),
        ] if text_parts else []
        if attachments:
            parts.append(FormattedAttachmentPart.from_attachments(attachments))
        return cls(parts = parts)

    def with_attachments(self, attachments: list[ChatAttachment]) -> FormattedChatMessage:
        parts = [
            part
            for part in self.parts
            if not isinstance(part, FormattedAttachmentPart)
        ]
        if attachments:
            parts.append(FormattedAttachmentPart.from_attachments(attachments))
        return FormattedChatMessage(parts = parts)

    def prepend_quote(self, message: FormattedChatMessage) -> FormattedChatMessage:
        return FormattedChatMessage(parts = [FormattedQuotePart(message = message, depth = 2), *self.parts])

    def to_text(self) -> str:
        return "\n\n".join(
            text
            for part in self.parts
            if (text := part.to_text())
        )
