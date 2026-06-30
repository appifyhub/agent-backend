import unittest
from datetime import date
from unittest.mock import Mock
from uuid import UUID

from api.model.credit_transfer_payload import CreditTransferPayload
from api.transfers_controller import TransfersController
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.users.user import User
from util.error_codes import INVALID_PLATFORM, NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


def _make_user(user_id: int, handle: str) -> User:
    return User(
        id = UUID(int = user_id),
        full_name = f"User {user_id}",
        telegram_username = handle,
        telegram_user_id = user_id,
        telegram_chat_id = str(user_id),
        group = UserDB.Group.standard,
        created_at = date.today(),
        credit_balance = 100.0,
    )


class TransfersControllerTest(unittest.TestCase):

    sender: User
    mock_di: DI

    def setUp(self):
        self.sender = _make_user(1, "sender_handle")

        self.mock_di = Mock(spec = DI)
        self.mock_di.invoker = self.sender
        self.mock_di.authorization_service.authorize_for_user.return_value = self.sender
        self.mock_di.credit_transfer_service.transfer_credits.return_value = None

    def test_transfer_success(self):
        payload = CreditTransferPayload(
            platform = "telegram",
            platform_handle = "receiver_handle",
            amount = 25.0,
        )

        controller = TransfersController(self.mock_di)
        controller.transfer_credits(self.sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_called_once()

    def test_transfer_delegates_to_service(self):
        payload = CreditTransferPayload(
            platform = "telegram",
            platform_handle = "receiver_handle",
            amount = 25.0,
            note = "Nice!",
        )

        controller = TransfersController(self.mock_di)
        controller.transfer_credits(self.sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_called_once_with(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 25.0,
            note = "Nice!",
        )

    def test_transfer_invalid_platform(self):
        payload = CreditTransferPayload(
            platform = "unknown_platform",
            platform_handle = "receiver_handle",
            amount = 25.0,
        )

        controller = TransfersController(self.mock_di)

        with self.assertRaises(ValidationError) as ctx:
            controller.transfer_credits(self.sender.id.hex, payload)

        self.assertEqual(ctx.exception.error_code, INVALID_PLATFORM)
        self.mock_di.credit_transfer_service.transfer_credits.assert_not_called()

    def test_transfer_authorization_failure(self):
        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError(
            "Unauthorized", NOT_TARGET_USER,
        )
        payload = CreditTransferPayload(
            platform = "telegram",
            platform_handle = "receiver_handle",
            amount = 25.0,
        )

        controller = TransfersController(self.mock_di)

        with self.assertRaises(AuthorizationError):
            controller.transfer_credits(self.sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_not_called()
