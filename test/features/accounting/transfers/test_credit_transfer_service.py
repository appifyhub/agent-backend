import unittest
from datetime import date
from unittest.mock import Mock
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.accounting.transfers.credit_transfer_service import CreditTransferService
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import TRANSFER_TOOL
from features.users.user import User
from util.error_codes import (
    INSUFFICIENT_CREDITS,
    INVALID_TRANSFER_AMOUNT,
    SELF_TRANSFER_NOT_ALLOWED,
    SPONSORED_USER_TRANSFER_NOT_ALLOWED,
    TRANSFER_RECIPIENT_NOT_FOUND,
    USER_NOT_FOUND,
)
from util.errors import NotFoundError, ValidationError


def _make_user(user_id: int, handle: str, credit_balance: float = 100.0) -> User:
    return User(
        id = UUID(int = user_id),
        full_name = f"User {user_id}",
        telegram_username = handle,
        telegram_user_id = user_id,
        telegram_chat_id = str(user_id),
        group = UserDB.Group.standard,
        created_at = date.today(),
        credit_balance = credit_balance,
    )


class CreditTransferServiceTest(unittest.TestCase):

    sender: User
    receiver: User
    mock_di: DI
    service: CreditTransferService

    def setUp(self):
        self.sender = _make_user(1, "sender_handle", credit_balance = 100.0)
        self.receiver = _make_user(2, "receiver_handle", credit_balance = 50.0)

        self.mock_di = Mock(spec = DI)
        self.mock_di.invoker_chat = None

        self.mock_di.user_repo.get.side_effect = lambda uid: (
            self.sender if uid == self.sender.id else
            self.receiver if uid == self.receiver.id else
            None
        )
        self.mock_di.user_repo.get_by_telegram_username.return_value = self.receiver
        self.mock_di.user_repo.update_locked_pair.return_value = None
        self.mock_di.sponsorship_repo.get_all_by_receiver.return_value = []
        self.mock_di.usage_record_repo.create.return_value = None
        self.mock_di.clone.side_effect = Exception("notification not configured in test")

        self.service = CreditTransferService(self.mock_di)

    def _get_created_record(self):
        self.mock_di.usage_record_repo.create.assert_called_once()
        return self.mock_di.usage_record_repo.create.call_args.args[0]

    def test_transfer_creates_single_usage_record(self):
        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 25.0,
        )

        record = self._get_created_record()
        self.assertEqual(record.user_id, self.sender.id)
        self.assertEqual(record.payer_id, self.sender.id)
        self.assertEqual(record.total_cost_credits, 25.0)
        self.assertEqual(record.tool, TRANSFER_TOOL)
        self.assertEqual(record.tool_purpose, ToolType.credit_transfer)
        self.assertEqual(record.counterpart_id, self.receiver.id)

    def test_transfer_record_participant_details(self):
        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
        )

        record = self._get_created_record()
        details = record.participant_details
        self.assertIsNotNone(details)
        self.assertEqual(details.payer.user_id, self.sender.id)
        self.assertEqual(details.payer.full_name, self.sender.full_name)
        self.assertEqual(details.counterpart.user_id, self.receiver.id)
        self.assertEqual(details.counterpart.full_name, self.receiver.full_name)
        self.assertEqual(details.owner.user_id, self.sender.id)
        self.assertEqual(details.owner.full_name, self.sender.full_name)

    def test_transfer_with_note(self):
        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
            note = "Thanks!",
        )

        record = self._get_created_record()
        self.assertEqual(record.note, "Thanks!")

    def test_transfer_amount_too_low(self):
        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 0.5,
            )

        self.assertEqual(ctx.exception.error_code, INVALID_TRANSFER_AMOUNT)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_sender_not_found(self):
        self.mock_di.user_repo.get.side_effect = None
        self.mock_di.user_repo.get.return_value = None

        with self.assertRaises(NotFoundError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, USER_NOT_FOUND)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_recipient_not_found(self):
        self.mock_di.user_repo.get_by_telegram_username.return_value = None

        with self.assertRaises(NotFoundError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "unknown_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, TRANSFER_RECIPIENT_NOT_FOUND)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_self_transfer_not_allowed(self):
        self.mock_di.user_repo.get_by_telegram_username.return_value = self.sender

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "sender_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SELF_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_sponsored_sender_not_allowed(self):
        self.mock_di.sponsorship_repo.get_all_by_receiver.side_effect = lambda uid, limit = 1: (
            [Mock()] if uid == self.sender.id else []
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_sponsored_receiver_not_allowed(self):
        self.mock_di.sponsorship_repo.get_all_by_receiver.side_effect = lambda uid, limit = 1: (
            [Mock()] if uid == self.receiver.id else []
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_insufficient_balance(self):
        broke_sender = _make_user(1, "sender_handle", credit_balance = 5.0)
        self.mock_di.user_repo.get.side_effect = lambda uid: (
            broke_sender if uid == broke_sender.id else
            self.receiver if uid == self.receiver.id else None
        )

        self.mock_di.user_repo.update_locked_pair.side_effect = (
            lambda first_id, second_id, update_fn: update_fn(broke_sender, self.receiver)
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = broke_sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, INSUFFICIENT_CREDITS)
        self.mock_di.user_repo.update_locked_pair.assert_called_once()
        self.mock_di.usage_record_repo.create.assert_not_called()

    def test_notification_failure_does_not_break_transfer(self):
        self.mock_di.clone.side_effect = RuntimeError("simulated notification failure")

        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
        )

        self.mock_di.usage_record_repo.create.assert_called_once()

    def test_transfer_calls_db_lock_with_correct_ids(self):
        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 30.0,
        )

        self.mock_di.user_repo.update_locked_pair.assert_called_once()
        args = self.mock_di.user_repo.update_locked_pair.call_args.args
        self.assertEqual(args[0], self.sender.id)
        self.assertEqual(args[1], self.receiver.id)
        self.assertTrue(callable(args[2]))
