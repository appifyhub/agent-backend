import unittest
from unittest.mock import Mock
from uuid import UUID

import stubs
from starlette.responses import StreamingResponse

from api.attachments_controller import AttachmentsController
from util.error_codes import ATTACHMENT_NOT_FOUND, NOT_CHAT_MEMBER
from util.errors import AuthorizationError, NotFoundError


class AttachmentsControllerTest(unittest.TestCase):

    def setUp(self):
        self.di = Mock()
        self.controller = AttachmentsController(self.di)

    def test_stream_private_attachment_returns_streaming_response(self):
        self.di.chat_attachment_service.stream_attachment.return_value = stubs.domain.resolved_attachment_stream(
            media_type = "image/png",
        )

        response = self.controller.stream_private_attachment("attachment-id")

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "image/png")
        self.di.chat_attachment_service.stream_attachment.assert_called_once_with("attachment-id")

    def test_stream_private_attachment_propagates_not_found(self):
        self.di.chat_attachment_service.stream_attachment.side_effect = NotFoundError(
            "Attachment 'missing' not found", ATTACHMENT_NOT_FOUND,
        )

        with self.assertRaises(NotFoundError):
            self.controller.stream_private_attachment("missing")

    def test_stream_private_attachment_propagates_non_member_error(self):
        self.di.chat_attachment_service.stream_attachment.side_effect = AuthorizationError(
            "Not a member", NOT_CHAT_MEMBER,
        )

        with self.assertRaises(AuthorizationError):
            self.controller.stream_private_attachment("attachment-id")

    def test_stream_public_attachment_returns_streaming_response(self):
        self.di.chat_attachment_service.stream_attachment.return_value = stubs.domain.resolved_attachment_stream(
            media_type = "image/png",
        )
        user = stubs.domain.user(id = UUID(int = 1))
        attachment = stubs.domain.chat_attachment(chat_id = UUID(int = 2))
        claims = stubs.api.public_attachment_token_claims(
            attachment_id = "attachment-id",
            chat_id = attachment.chat_id.hex,
            issuer_user_id = user.id.hex,
        )

        response = self.controller.stream_public_attachment(claims)

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "image/png")
        self.di.chat_attachment_service.stream_attachment.assert_called_once_with("attachment-id")

    def test_stream_public_attachment_propagates_not_found(self):
        self.di.chat_attachment_service.stream_attachment.side_effect = NotFoundError(
            "Attachment 'missing' not found", ATTACHMENT_NOT_FOUND,
        )
        user = stubs.domain.user(id = UUID(int = 1))
        attachment = stubs.domain.chat_attachment(chat_id = UUID(int = 2))
        claims = stubs.api.public_attachment_token_claims(
            attachment_id = "missing",
            chat_id = attachment.chat_id.hex,
            issuer_user_id = user.id.hex,
        )

        with self.assertRaises(NotFoundError):
            self.controller.stream_public_attachment(claims)

    def test_stream_public_attachment_propagates_non_member_error(self):
        self.di.chat_attachment_service.stream_attachment.side_effect = AuthorizationError(
            "Not a member", NOT_CHAT_MEMBER,
        )
        user = stubs.domain.user(id = UUID(int = 1))
        attachment = stubs.domain.chat_attachment(chat_id = UUID(int = 2))
        claims = stubs.api.public_attachment_token_claims(
            attachment_id = "attachment-id",
            chat_id = attachment.chat_id.hex,
            issuer_user_id = user.id.hex,
        )

        with self.assertRaises(AuthorizationError):
            self.controller.stream_public_attachment(claims)
