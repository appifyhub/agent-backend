import unittest
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from jose import jwt
from starlette.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from api.auth import (
    create_jwt_token,
    create_public_resource_token,
)
from db.sql import get_session
from features.chat.attachment.attachment_service import ATTACHMENT_PUBLIC_READ_PURPOSE, AttachmentService
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.membership.chat_membership import ChatMembership
from features.users.user import User
from main import app
from util.error_codes import ATTACHMENT_NOT_FOUND, INVALID_RESOURCE_TOKEN, NOT_CHAT_MEMBER


class FakeDI:

    def __init__(
        self,
        invoker: User | None,
        attachment: ChatMessageAttachment | None,
        content: bytes = b"stored attachment",
        membership: ChatMembership | None = None,
    ):
        self.invoker = invoker
        self.chat_message_attachment_repo = Mock()
        self.chat_message_attachment_repo.get.return_value = attachment
        self.chat_membership_service = Mock()
        self.chat_membership_service.get.return_value = membership
        self.attachment_storage = Mock()
        self.attachment_storage.open.side_effect = lambda _: BytesIO(content)
        self.attachment_service = AttachmentService(self)


class AttachmentsControllerTest(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_session] = lambda: None
        self.client = TestClient(app)
        self.user = User(id = UUID(int = 1))
        self.attachment = ChatMessageAttachment(
            id = "attachment-id",
            chat_id = UUID(int = 2),
            message_id = "message-id",
            extension = "png",
            mime_type = "image/png",
        )
        self.membership = ChatMembership(user_id = self.user.id, chat_id = self.attachment.chat_id)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_private_endpoint_streams_attachment_for_chat_member(self):
        di = FakeDI(
            invoker = self.user,
            attachment = self.attachment,
            content = b"private-content",
            membership = self.membership,
        )
        token = create_jwt_token({"sub": self.user.id.hex}, expires_in = timedelta(minutes = 1))

        with patch("main.DI", return_value = di):
            response = self.client.get(
                "/attachments/private/attachment-id",
                headers = {"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.content, b"private-content")
        self.assertEqual(response.headers["content-type"], "image/png")
        di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        di.chat_membership_service.get.assert_called_once_with(self.user.id, self.attachment.chat_id)
        di.attachment_storage.open.assert_called_once_with(self.attachment)

    def test_private_endpoint_rejects_missing_authentication(self):
        response = self.client.get("/attachments/private/attachment-id")

        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_private_endpoint_rejects_non_member(self):
        di = FakeDI(invoker = self.user, attachment = self.attachment, membership = None)
        token = create_jwt_token({"sub": self.user.id.hex}, expires_in = timedelta(minutes = 1))

        with patch("main.DI", return_value = di):
            response = self.client.get(
                "/attachments/private/attachment-id",
                headers = {"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error_code"], NOT_CHAT_MEMBER)
        di.attachment_storage.open.assert_not_called()

    def test_public_endpoint_streams_attachment_with_valid_token(self):
        di = FakeDI(
            invoker = self.user,
            attachment = self.attachment,
            content = b"public-content",
            membership = self.membership,
        )
        token = create_public_resource_token(
            "attachment-id",
            ATTACHMENT_PUBLIC_READ_PURPOSE,
            self.user.id.hex,
            ttl_seconds = 60,
        )

        with patch("main.DI", return_value = di) as di_factory:
            response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.content, b"public-content")
        self.assertEqual(response.headers["content-type"], "image/png")
        di_factory.assert_called_once_with(None, self.user.id.hex)
        di.chat_message_attachment_repo.get.assert_called_once_with("attachment-id")
        di.chat_membership_service.get.assert_called_once_with(self.user.id, self.attachment.chat_id)
        di.attachment_storage.open.assert_called_once_with(self.attachment)

    def test_public_endpoint_rejects_expired_token(self):
        token = create_jwt_token(
            {
                "principal_id": self.user.id.hex,
                "resource_id": "attachment-id",
                "purpose": ATTACHMENT_PUBLIC_READ_PURPOSE,
            },
            timedelta(seconds = -1),
        )

        response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error_code"], INVALID_RESOURCE_TOKEN)

    def test_public_endpoint_rejects_wrong_purpose_token(self):
        token = create_jwt_token(
            {
                "principal_id": self.user.id.hex,
                "resource_id": "attachment-id",
                "purpose": "settings",
            },
            expires_in = timedelta(minutes = 1),
        )

        response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error_code"], INVALID_RESOURCE_TOKEN)

    def test_public_endpoint_rejects_principal_without_chat_membership(self):
        di = FakeDI(invoker = self.user, attachment = self.attachment, membership = None)
        token = create_public_resource_token(
            "attachment-id",
            ATTACHMENT_PUBLIC_READ_PURPOSE,
            self.user.id.hex,
            ttl_seconds = 60,
        )

        with patch("main.DI", return_value = di):
            response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error_code"], NOT_CHAT_MEMBER)
        di.chat_membership_service.get.assert_called_once_with(self.user.id, self.attachment.chat_id)
        di.attachment_storage.open.assert_not_called()

    def test_public_endpoint_rejects_missing_attachment(self):
        di = FakeDI(invoker = None, attachment = None)
        token = create_public_resource_token(
            "missing-id",
            ATTACHMENT_PUBLIC_READ_PURPOSE,
            self.user.id.hex,
            ttl_seconds = 60,
        )

        with patch("main.DI", return_value = di):
            response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["error_code"], ATTACHMENT_NOT_FOUND)
        di.attachment_storage.open.assert_not_called()

    def test_public_endpoint_rejects_unsigned_token(self):
        token = jwt.encode(
            {
                "principal_id": self.user.id.hex,
                "resource_id": "attachment-id",
                "purpose": ATTACHMENT_PUBLIC_READ_PURPOSE,
            },
            "wrong-secret",
            algorithm = "HS256",
        )

        response = self.client.get(f"/attachments/public/{token}")

        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error_code"], INVALID_RESOURCE_TOKEN)
