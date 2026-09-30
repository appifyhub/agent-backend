from unittest import IsolatedAsyncioTestCase

import stubs
from util.di_utils import di_for_tests

from api.attachments_controller import AttachmentsController
from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from util.error_codes import ATTACHMENT_NOT_FOUND, NOT_CHAT_MEMBER
from util.errors import AuthorizationError, NotFoundError


class AttachmentsControllerTest(IsolatedAsyncioTestCase):

    di: DI
    controller: AttachmentsController
    attachment: ChatAttachment

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config()))
        self.attachment = self.di.chat_attachment_service.save(stubs.domain.chat_attachment(), content = b"image data")
        self.controller = AttachmentsController(self.di)

    async def test_stream_private_attachment_returns_streaming_response(self):
        self.di.chat_membership_service.save(stubs.domain.chat_membership())

        response = self.controller.stream_private_attachment(self.attachment.id)

        self.assertEqual(response.media_type, self.attachment.mime_type)
        self.assertEqual(b"".join([chunk async for chunk in response.body_iterator]), b"image data")

    def test_stream_private_attachment_propagates_not_found(self):
        with self.assertRaises(NotFoundError) as context:
            self.controller.stream_private_attachment("missing")

        self.assertEqual(context.exception.error_code, ATTACHMENT_NOT_FOUND)

    def test_stream_private_attachment_propagates_non_member_error(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.stream_private_attachment(self.attachment.id)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)

    async def test_stream_public_attachment_returns_streaming_response(self):
        self.di.chat_membership_service.save(stubs.domain.chat_membership())
        claims = stubs.api.public_attachment_token_claims(attachment_id = self.attachment.id)

        response = self.controller.stream_public_attachment(claims)

        self.assertEqual(response.media_type, self.attachment.mime_type)
        self.assertEqual(b"".join([chunk async for chunk in response.body_iterator]), b"image data")

    def test_stream_public_attachment_propagates_not_found(self):
        claims = stubs.api.public_attachment_token_claims(attachment_id = "missing")

        with self.assertRaises(NotFoundError) as context:
            self.controller.stream_public_attachment(claims)

        self.assertEqual(context.exception.error_code, ATTACHMENT_NOT_FOUND)

    def test_stream_public_attachment_propagates_non_member_error(self):
        claims = stubs.api.public_attachment_token_claims(attachment_id = self.attachment.id)

        with self.assertRaises(AuthorizationError) as context:
            self.controller.stream_public_attachment(claims)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
