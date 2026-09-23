import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from uuid import UUID

import stubs

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.transfers.credit_transfer_service import CreditTransferService
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import TRANSFER_TOOL
from features.integrations.integration_config import THE_AGENT
from features.users.user import User
from util.error_codes import (
    INSUFFICIENT_CREDITS,
    INVALID_TRANSFER_AMOUNT,
    SELF_TRANSFER_NOT_ALLOWED,
    SPONSORED_USER_TRANSFER_NOT_ALLOWED,
    TRANSFER_FAILED,
    TRANSFER_RECIPIENT_NOT_FOUND,
    USER_NOT_FOUND,
)
from util.errors import InternalError, NotFoundError, ValidationError


class CreditTransferServiceTest(unittest.TestCase):

    mock_di: DI
    service: CreditTransferService

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.mock_di.invoker_chat = None

        self.mock_di.user_repo.update_locked_pair.return_value = None
        self.mock_di.sponsorship_repo.get_all_by_receiver.return_value = []
        self.mock_di.usage_record_repo.create.return_value = None
        self.mock_di.clone.side_effect = Exception("notification not configured in test")

        self.service = CreditTransferService(self.mock_di)

    def _get_created_record(self):
        self.mock_di.usage_record_repo.create.assert_called_once()
        return self.mock_di.usage_record_repo.create.call_args.args[0]

    def test_transfer_creates_single_usage_record(self):
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver

        self.service.transfer_credits(
            sender_id = sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 25.0,
        )

        record = self._get_created_record()
        self.assertEqual(record.user_id, sender.id)
        self.assertEqual(record.payer_id, sender.id)
        self.assertEqual(record.total_cost_credits, 25.0)
        self.assertEqual(record.tool, TRANSFER_TOOL)
        self.assertEqual(record.tool_purpose, ToolType.credit_transfer)
        self.assertEqual(record.counterpart_id, receiver.id)

    def test_transfer_record_participant_details(self):
        sender = stubs.domain.user(full_name = "Sender User")
        receiver = stubs.domain.user(id = UUID(int = 2), full_name = "Receiver User")
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver

        self.service.transfer_credits(
            sender_id = sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
        )

        record = self._get_created_record()
        details = record.participant_details
        self.assertIsNotNone(details)
        self.assertEqual(details.payer.user_id, sender.id)
        self.assertEqual(details.payer.full_name, sender.full_name)
        self.assertEqual(details.counterpart.user_id, receiver.id)
        self.assertEqual(details.counterpart.full_name, receiver.full_name)
        self.assertEqual(details.owner.user_id, sender.id)
        self.assertEqual(details.owner.full_name, sender.full_name)

    def test_transfer_with_note(self):
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver

        self.service.transfer_credits(
            sender_id = sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
            note = "Thanks!",
        )

        record = self._get_created_record()
        self.assertEqual(record.note, "Thanks!")

    def test_transfer_amount_too_low(self):
        sender_id = UUID(int = 1)

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = sender_id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 0.5,
            )

        self.assertEqual(ctx.exception.error_code, INVALID_TRANSFER_AMOUNT)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_sender_not_found(self):
        self.mock_di.user_repo.get.side_effect = None
        self.mock_di.user_repo.get.return_value = None

        sender_id = UUID(int = 1)
        with self.assertRaises(NotFoundError) as ctx:
            self.service.transfer_credits(
                sender_id = sender_id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, USER_NOT_FOUND)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_recipient_not_found(self):
        sender = stubs.domain.user()
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = None

        with self.assertRaises(NotFoundError) as ctx:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "unknown_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, TRANSFER_RECIPIENT_NOT_FOUND)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_self_transfer_not_allowed(self):
        sender = stubs.domain.user()
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = sender

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "sender_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SELF_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_sponsored_sender_not_allowed(self):
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver
        self.mock_di.sponsorship_repo.get_all_by_receiver.side_effect = lambda uid, limit = 1: (
            [stubs.domain.sponsorship()] if uid == sender.id else []
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_sponsored_receiver_not_allowed(self):
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver
        self.mock_di.sponsorship_repo.get_all_by_receiver.side_effect = lambda uid, limit = 1: (
            [stubs.domain.sponsorship()] if uid == receiver.id else []
        )

        with self.assertRaises(ValidationError) as ctx:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(ctx.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.mock_di.user_repo.update_locked_pair.assert_not_called()

    def test_transfer_insufficient_balance(self):
        broke_sender = stubs.domain.user(credit_balance = 5.0)
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = broke_sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver

        self.mock_di.user_repo.update_locked_pair.side_effect = (
            lambda first_id, second_id, update_fn: update_fn(broke_sender, receiver)
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
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver
        self.mock_di.clone.side_effect = RuntimeError("simulated notification failure")

        self.service.transfer_credits(
            sender_id = sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
        )

        self.mock_di.usage_record_repo.create.assert_called_once()

    def test_transfer_calls_db_lock_with_correct_ids(self):
        sender = stubs.domain.user()
        receiver = stubs.domain.user(id = UUID(int = 2))
        self.mock_di.user_repo.get.return_value = sender
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver
        self.service.transfer_credits(
            sender_id = sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 30.0,
        )

        self.mock_di.user_repo.update_locked_pair.assert_called_once()
        args = self.mock_di.user_repo.update_locked_pair.call_args.args
        self.assertEqual(args[0], sender.id)
        self.assertEqual(args[1], receiver.id)
        self.assertTrue(callable(args[2]))

    def _fake_update_locked_for_grant(self, recipient: User) -> tuple[User, list[tuple[User, User]]]:
        grant_agent = replace(THE_AGENT, credit_balance = 0.0)
        grant_pair_results: list[tuple[User, User]] = []
        users = {
            grant_agent.id: grant_agent,
            recipient.id: recipient,
        }

        def fake(first_id, second_id, update_fn, commit = True):
            result = update_fn(users[first_id], users[second_id])
            users[first_id], users[second_id] = result
            grant_pair_results.append(result)
            return result

        self.mock_di.user_repo.update_locked_pair.side_effect = fake
        return grant_agent, grant_pair_results

    def test_credit_grant_accepts_recipient_id(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        self._fake_update_locked_for_grant(recipient)

        updated = self.service.grant_credits(
            recipient = recipient.id,
            amount = 125.0,
            commit = True,
        )

        self.assertEqual(updated.credit_balance, 125.0)

    def test_credit_grant_accepts_recipient_user_and_preserves_existing_balance(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 250.0)
        self._fake_update_locked_for_grant(recipient)

        updated = self.service.grant_credits(
            recipient = recipient,
            amount = 75.0,
            commit = True,
        )

        self.assertEqual(updated.credit_balance, 325.0)

    def test_credit_grant_funds_agent_then_transfers_and_commits(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        grant_agent, grant_pair_results = self._fake_update_locked_for_grant(recipient)

        self.service.grant_credits(
            recipient = recipient,
            amount = 50.0,
            commit = True,
        )

        calls = self.mock_di.user_repo.update_locked_pair.call_args_list
        self.assertEqual(len(calls), 2)
        for locked_pair_call in calls:
            if locked_pair_call.args:
                first_id, second_id, update_fn = locked_pair_call.args
            else:
                first_id = locked_pair_call.kwargs["first_id"]
                second_id = locked_pair_call.kwargs["second_id"]
                update_fn = locked_pair_call.kwargs["update_fn"]
            self.assertEqual(first_id, THE_AGENT.id)
            self.assertEqual(second_id, recipient.id)
            self.assertTrue(callable(update_fn))
            self.assertFalse(locked_pair_call.kwargs["commit"])
        self.assertEqual(grant_pair_results[0][0].credit_balance, 50.0)
        self.assertEqual(grant_pair_results[1][0].credit_balance, grant_agent.credit_balance)
        self.mock_di.db.commit.assert_called_once()
        self.mock_di.db.rollback.assert_not_called()

    def test_credit_grant_defers_commit_and_notification_when_requested(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        self._fake_update_locked_for_grant(recipient)

        with patch.object(self.service, "notify_grant") as notify:
            updated = self.service.grant_credits(
                recipient = recipient,
                amount = 50.0,
                commit = False,
            )

        self.assertEqual(updated.credit_balance, 50.0)
        self.mock_di.db.commit.assert_not_called()
        notify.assert_not_called()

    def test_credit_grant_creates_transfer_history_record(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        _, grant_pair_results = self._fake_update_locked_for_grant(recipient)

        with patch.object(self.service, "_CreditTransferService__try_to_send_notification") as notify:
            self.service.grant_credits(
                recipient = recipient,
                amount = 500.0,
                note = "Welcome",
                commit = True,
            )

        record = self._get_created_record()
        self.assertEqual(record.user_id, THE_AGENT.id)
        self.assertEqual(record.payer_id, THE_AGENT.id)
        self.assertEqual(record.counterpart_id, recipient.id)
        self.assertEqual(record.note, "Welcome")
        self.assertTrue(record.uses_credits)
        self.assertEqual(record.total_cost_credits, 500.0)
        self.mock_di.usage_record_repo.create.assert_called_once_with(record, commit = False)
        notify.assert_called_once_with(
            grant_pair_results[1][1],
            "You have been granted 500.0 credits for \"Welcome\". Enjoy!",
        )

    def test_credit_grant_note_defaults_to_none(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        _, grant_pair_results = self._fake_update_locked_for_grant(recipient)

        with patch.object(self.service, "_CreditTransferService__try_to_send_notification") as notify:
            self.service.grant_credits(
                recipient = recipient,
                amount = 25.0,
                commit = True,
            )

        self.assertIsNone(self._get_created_record().note)
        notify.assert_called_once_with(
            grant_pair_results[1][1],
            "You have been granted 25.0 credits. Enjoy!",
        )

    def test_credit_grant_rolls_back_when_record_creation_fails(self):
        recipient = stubs.domain.user(id = UUID(int = 99), credit_balance = 0.0)
        self._fake_update_locked_for_grant(recipient)
        expected = InternalError("Record creation failed", TRANSFER_FAILED)
        self.mock_di.usage_record_repo.create.side_effect = expected

        with self.assertRaises(InternalError) as context:
            self.service.grant_credits(
                recipient = recipient,
                amount = 25.0,
                commit = True,
            )

        self.assertIs(context.exception, expected)
        self.mock_di.db.commit.assert_not_called()
        self.mock_di.db.rollback.assert_called_once()

    def test_credit_grant_rejects_unpersisted_user(self):
        recipient = stubs.domain.user(id = None)

        with self.assertRaises(NotFoundError) as context:
            self.service.grant_credits(
                recipient = recipient,
                amount = 25.0,
                commit = True,
            )

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)
