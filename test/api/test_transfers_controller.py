import unittest
from unittest.mock import Mock
from uuid import UUID

import stubs

from api.transfers_controller import TransfersController
from db.model.chat_config import ChatConfigDB
from di.di import DI
from util.error_codes import INVALID_PLATFORM, NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class TransfersControllerTest(unittest.TestCase):

    mock_di: DI

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.mock_di.credit_transfer_service.transfer_credits.return_value = None

    def test_transfer_success(self):
        sender = stubs.domain.user(id = UUID(int = 1))
        self.mock_di.invoker = sender
        self.mock_di.authorization_service.authorize_for_user.return_value = sender

        payload = stubs.api.credit_transfer_payload()

        controller = TransfersController(self.mock_di)
        controller.transfer_credits(sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_called_once()

    def test_transfer_delegates_to_service(self):
        sender = stubs.domain.user(id = UUID(int = 1))
        self.mock_di.invoker = sender
        self.mock_di.authorization_service.authorize_for_user.return_value = sender

        payload = stubs.api.credit_transfer_payload(note = "Nice!")

        controller = TransfersController(self.mock_di)
        controller.transfer_credits(sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_called_once_with(
            sender_id = sender.id,
            recipient_handle = payload.platform_handle,
            chat_type = ChatConfigDB.ChatType(payload.platform),
            amount = payload.amount,
            note = payload.note,
        )

    def test_transfer_invalid_platform(self):
        sender = stubs.domain.user(id = UUID(int = 1))
        self.mock_di.invoker = sender
        self.mock_di.authorization_service.authorize_for_user.return_value = sender

        payload = stubs.api.credit_transfer_payload(platform = "unknown_platform")

        controller = TransfersController(self.mock_di)

        with self.assertRaises(ValidationError) as ctx:
            controller.transfer_credits(sender.id.hex, payload)

        self.assertEqual(ctx.exception.error_code, INVALID_PLATFORM)
        self.mock_di.credit_transfer_service.transfer_credits.assert_not_called()

    def test_transfer_authorization_failure(self):
        sender = stubs.domain.user(id = UUID(int = 1))
        self.mock_di.invoker = sender
        self.mock_di.authorization_service.authorize_for_user.return_value = sender

        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError(
            "Unauthorized", NOT_TARGET_USER,
        )
        payload = stubs.api.credit_transfer_payload()

        controller = TransfersController(self.mock_di)

        with self.assertRaises(AuthorizationError):
            controller.transfer_credits(sender.id.hex, payload)

        self.mock_di.credit_transfer_service.transfer_credits.assert_not_called()
