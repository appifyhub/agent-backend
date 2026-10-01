from unittest import TestCase
from uuid import UUID

import stubs
from util.di_utils import di_for_tests

from api.transfers_controller import TransfersController
from di.di import DI
from features.users.user import User
from util.error_codes import INVALID_PLATFORM, NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class TransfersControllerTest(TestCase):

    di: DI
    controller: TransfersController
    sender: User
    receiver: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.sender = self.di.user_repo.save(stubs.domain.user())
        self.receiver = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_username = "receiver_handle",
            telegram_user_id = 987654321,
            whatsapp_user_id = None,
            connect_key = "RECEIVER-KEY",
        ))
        self.di.inject_invoker(self.sender)
        self.controller = self.di.transfers_controller

    def test_transfer_success(self):
        payload = stubs.api.credit_transfer_payload()

        self.controller.transfer_credits(self.sender.id.hex, payload)

        self.assertEqual(self.di.user_repo.get(self.sender.id).credit_balance, self.sender.credit_balance - payload.amount)
        self.assertEqual(self.di.user_repo.get(self.receiver.id).credit_balance, self.receiver.credit_balance + payload.amount)

    def test_transfer_preserves_note(self):
        payload = stubs.api.credit_transfer_payload(note = "Nice!")

        self.controller.transfer_credits(self.sender.id.hex, payload)

        records = self.di.usage_record_repo.get_by_user(self.sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].note, payload.note)
        self.assertEqual(records[0].counterpart_id, self.receiver.id)
        self.assertEqual(records[0].total_cost_credits, payload.amount)

    def test_transfer_invalid_platform(self):
        payload = stubs.api.credit_transfer_payload(platform = "unknown_platform")

        with self.assertRaises(ValidationError) as context:
            self.controller.transfer_credits(self.sender.id.hex, payload)

        self.assertEqual(context.exception.error_code, INVALID_PLATFORM)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)

    def test_transfer_authorization_failure(self):
        payload = stubs.api.credit_transfer_payload()

        with self.assertRaises(AuthorizationError) as context:
            self.controller.transfer_credits(self.receiver.id.hex, payload)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
