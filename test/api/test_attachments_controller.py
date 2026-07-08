import unittest
from io import BytesIO
from unittest.mock import Mock
from uuid import UUID

from starlette.responses import StreamingResponse

from api.attachments_controller import AttachmentsController
from api.auth import PublicAttachmentTokenClaims
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_service import ResolvedAttachmentStream
from features.chat.membership.chat_membership import ChatMembership
from features.users.user import User
from util.error_codes import ATTACHMENT_NOT_FOUND, NOT_CHAT_MEMBER
from util.errors import AuthorizationError, NotFoundError


class AttachmentsControllerTest(unittest.TestCase):

    def setUp(self):
        self.user = User(id = UUID(int = 1))
        self.attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            uploader_user_id = self.user.id,
            message_id = "message-id",
            extension = "png",
            mime_type = "image/png",
        )
        self.membership = ChatMembership(user_id = self.user.id, chat_id = self.attachment.chat_id)
        self.di = Mock()
        self.controller = AttachmentsController(self.di)

    def test_stream_private_attachment_returns_streaming_response(self):
        self.di.chat_message_attachment_service.stream_attachment.return_value = ResolvedAttachmentStream(
            stream = BytesIO(b"private-content"),
            media_type = "image/png",
        )

        response = self.controller.stream_private_attachment("attachment-id")

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "image/png")
        self.di.chat_message_attachment_service.stream_attachment.assert_called_once_with("attachment-id")

    def test_stream_private_attachment_propagates_not_found(self):
        self.di.chat_message_attachment_service.stream_attachment.side_effect = NotFoundError(
            "Attachment 'missing' not found", ATTACHMENT_NOT_FOUND,
        )

        with self.assertRaises(NotFoundError):
            self.controller.stream_private_attachment("missing")

    def test_stream_private_attachment_propagates_non_member_error(self):
        self.di.chat_message_attachment_service.stream_attachment.side_effect = AuthorizationError(
            "Not a member", NOT_CHAT_MEMBER,
        )

        with self.assertRaises(AuthorizationError):
            self.controller.stream_private_attachment("attachment-id")

    def test_stream_public_attachment_returns_streaming_response(self):
        self.di.chat_message_attachment_service.stream_attachment.return_value = ResolvedAttachmentStream(
            stream = BytesIO(b"public-content"),
            media_type = "image/png",
        )
        claims = PublicAttachmentTokenClaims(
            attachment_id = "attachment-id",
            chat_id = self.attachment.chat_id.hex,
            issuer_user_id = self.user.id.hex,
        )

        response = self.controller.stream_public_attachment(claims)

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "image/png")
        self.di.chat_message_attachment_service.stream_attachment.assert_called_once_with("attachment-id")

    def test_stream_public_attachment_propagates_not_found(self):
        self.di.chat_message_attachment_service.stream_attachment.side_effect = NotFoundError(
            "Attachment 'missing' not found", ATTACHMENT_NOT_FOUND,
        )
        claims = PublicAttachmentTokenClaims(
            attachment_id = "missing",
            chat_id = self.attachment.chat_id.hex,
            issuer_user_id = self.user.id.hex,
        )

        with self.assertRaises(NotFoundError):
            self.controller.stream_public_attachment(claims)

    def test_stream_public_attachment_propagates_non_member_error(self):
        self.di.chat_message_attachment_service.stream_attachment.side_effect = AuthorizationError(
            "Not a member", NOT_CHAT_MEMBER,
        )
        claims = PublicAttachmentTokenClaims(
            attachment_id = "attachment-id",
            chat_id = self.attachment.chat_id.hex,
            issuer_user_id = self.user.id.hex,
        )

        with self.assertRaises(AuthorizationError):
            self.controller.stream_public_attachment(claims)
