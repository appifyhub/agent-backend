from dataclasses import replace
from datetime import datetime
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.transfers.credit_transfer_service import CreditTransferService
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import TRANSFER_TOOL
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integration_config import THE_AGENT
from features.users.user import User
from util.error_codes import (
    INSUFFICIENT_CREDITS,
    INVALID_TRANSFER_AMOUNT,
    SELF_TRANSFER_NOT_ALLOWED,
    SPONSORED_USER_TRANSFER_NOT_ALLOWED,
    TRANSFER_RECIPIENT_NOT_FOUND,
    UNEXPECTED_ERROR,
    USER_NOT_FOUND,
)
from util.errors import ExternalServiceError, NotFoundError, ValidationError


class CreditTransferServiceTest(TestCase):

    di: DI
    service: CreditTransferService
    sender: User
    receiver: User
    agent: User
    model: FakeChatModel
    api: FakeTelegramBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.credit_transfer_service
        self.sender = self.di.user_repo.save(stubs.domain.user(
            telegram_username = "sender_handle",
        ))
        self.receiver = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            full_name = "Receiver User",
            telegram_username = "receiver_handle",
            telegram_user_id = 987654321,
            telegram_chat_id = "987654321",
            whatsapp_user_id = None,
            connect_key = "RECEIVER-KEY",
        ))
        self.agent = self.di.user_repo.save(stubs.domain.user(
            id = THE_AGENT.id,
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "AGENT-KEY",
        ))
        self.di.inject_invoker(self.sender)
        tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(tool))
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)

    def test_transfer_moves_credits_and_creates_single_usage_record(self):
        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 25.0,
        )

        self.assertEqual(self.di.user_repo.get(self.sender.id), replace(self.sender, credit_balance = 75.0))
        self.assertEqual(self.di.user_repo.get(self.receiver.id), replace(self.receiver, credit_balance = 125.0))
        records = self.di.usage_record_repo.get_by_user(self.sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        record = records[0]
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

        records = self.di.usage_record_repo.get_by_user(self.sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        details = records[0].participant_details
        self.assertIsNotNone(details)
        assert details is not None
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

        records = self.di.usage_record_repo.get_by_user(self.sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].note, "Thanks!")

    def test_transfer_amount_too_low(self):
        with self.assertRaises(ValidationError) as context:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 0.5,
            )

        self.assertEqual(context.exception.error_code, INVALID_TRANSFER_AMOUNT)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.sender.id), [])

    def test_transfer_sender_not_found(self):
        sender_id = UUID("44444444-4444-4444-8444-d44444444444")

        with self.assertRaises(NotFoundError) as context:
            self.service.transfer_credits(
                sender_id = sender_id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
        self.assertEqual(self.di.usage_record_repo.get_by_user(sender_id), [])

    def test_transfer_recipient_not_found(self):
        with self.assertRaises(NotFoundError) as context:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "unknown_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, TRANSFER_RECIPIENT_NOT_FOUND)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.sender.id), [])

    def test_self_transfer_not_allowed(self):
        with self.assertRaises(ValidationError) as context:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "sender_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, SELF_TRANSFER_NOT_ALLOWED)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.sender.id), [])

    def test_sponsored_sender_not_allowed(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.receiver.id,
            receiver_id = self.sender.id,
        ))

        with self.assertRaises(ValidationError) as context:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.sender.id), [])

    def test_sponsored_receiver_not_allowed(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sender.id,
            receiver_id = self.receiver.id,
        ))

        with self.assertRaises(ValidationError) as context:
            self.service.transfer_credits(
                sender_id = self.sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, SPONSORED_USER_TRANSFER_NOT_ALLOWED)
        self.assertEqual(self.di.user_repo.get(self.sender.id), self.sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.sender.id), [])

    def test_transfer_insufficient_balance(self):
        sender = self.di.user_repo.save(replace(self.sender, credit_balance = 5.0))

        with self.assertRaises(ValidationError) as context:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 10.0,
            )

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.di.user_repo.get(sender.id), sender)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), self.receiver)
        self.assertEqual(self.di.usage_record_repo.get_by_user(sender.id), [])

    def test_notification_failure_does_not_break_transfer(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.sender.telegram_chat_id))
        self.model.responses.append(stubs.external.ai_message(content = "Transfer sent."))
        self.api.delivery_errors[str(chat.external_id)] = ExternalServiceError("Delivery failed", UNEXPECTED_ERROR)

        self.service.transfer_credits(
            sender_id = self.sender.id,
            recipient_handle = "receiver_handle",
            chat_type = ChatConfigDB.ChatType.telegram,
            amount = 10.0,
        )

        self.assertEqual(self.di.user_repo.get(self.sender.id), replace(self.sender, credit_balance = 90.0))
        self.assertEqual(self.di.user_repo.get(self.receiver.id), replace(self.receiver, credit_balance = 110.0))
        records = self.di.usage_record_repo.get_by_user(self.sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].total_cost_credits, 10.0)
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.api.get_sent_messages(str(chat.external_id)), [])

    def test_unfunded_notification_does_not_break_committed_transfer(self):
        sender = self.di.user_repo.save(replace(
            self.sender,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = sender.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = sender.id, chat_id = chat.chat_id))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = sender.id,
            message_id = "transfer-message",
            sent_at = datetime.now(),
        ))
        api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)

        with patch("features.accounting.transfers.credit_transfer_service.log.w") as warning_log:
            self.service.transfer_credits(
                sender_id = sender.id,
                recipient_handle = "receiver_handle",
                chat_type = ChatConfigDB.ChatType.telegram,
                amount = 100.0,
            )

        self.assertEqual(self.di.user_repo.get(sender.id).credit_balance, 0.0)
        self.assertEqual(self.di.user_repo.get(self.receiver.id).credit_balance, 200.0)
        records = self.di.usage_record_repo.get_by_user(sender.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].total_cost_credits, 100.0)
        self.assertEqual(len(self.model.prompts), 0)
        self.assertEqual(api.get_sent_messages(str(chat.external_id)), [])
        warning_log.assert_called_once_with(f"Skipping transfer notification for user {sender.id.hex} due to insufficient delivery credits")  # ruff: ignore[line-too-long]

    def test_credit_grant_accepts_recipient_id(self):
        updated = self.service.grant_credits(
            recipient = self.receiver.id,
            amount = 125.0,
            commit = True,
        )

        self.assertEqual(updated, replace(self.receiver, credit_balance = 225.0))
        self.assertEqual(self.di.user_repo.get(self.receiver.id), updated)

    def test_credit_grant_accepts_recipient_user_and_preserves_existing_balance(self):
        recipient = self.di.user_repo.save(replace(self.receiver, credit_balance = 250.0))

        updated = self.service.grant_credits(
            recipient = recipient,
            amount = 75.0,
            commit = True,
        )

        self.assertEqual(updated, replace(recipient, credit_balance = 325.0))
        self.assertEqual(self.di.user_repo.get(recipient.id), updated)

    def test_credit_grant_preserves_agent_balance(self):
        updated = self.service.grant_credits(
            recipient = self.receiver,
            amount = 50.0,
            commit = True,
        )

        self.assertEqual(updated.credit_balance, 150.0)
        self.assertEqual(self.di.user_repo.get(self.receiver.id), updated)
        self.assertEqual(self.di.user_repo.get(self.agent.id), self.agent)

    def test_credit_grant_defers_notification_when_requested(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.receiver.telegram_chat_id))
        self.model.responses.append(stubs.external.ai_message(content = "Credits granted."))

        updated = self.service.grant_credits(
            recipient = self.receiver,
            amount = 50.0,
            commit = False,
        )

        self.assertEqual(updated.credit_balance, 150.0)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.api.get_sent_messages(str(chat.external_id)), [])

    def test_credit_grant_creates_transfer_history_record(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.receiver.telegram_chat_id))
        self.model.responses.append(stubs.external.ai_message(content = "Welcome credits granted."))

        self.service.grant_credits(
            recipient = self.receiver,
            amount = 500.0,
            note = "Welcome",
            commit = True,
        )

        records = self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.user_id, THE_AGENT.id)
        self.assertEqual(record.payer_id, THE_AGENT.id)
        self.assertEqual(record.counterpart_id, self.receiver.id)
        self.assertEqual(record.note, "Welcome")
        self.assertTrue(record.uses_credits)
        self.assertEqual(record.total_cost_credits, 500.0)
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(
            self.model.prompts[0][-1].content,
            "You have been granted 500.0 credits for \"Welcome\". Enjoy!",
        )
        self.assertEqual(
            [message["text"] for message in self.api.get_sent_messages(str(chat.external_id))],
            ["Welcome credits granted."],
        )

    def test_credit_grant_note_defaults_to_none(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.receiver.telegram_chat_id))
        self.model.responses.append(stubs.external.ai_message(content = "Credits granted."))

        self.service.grant_credits(
            recipient = self.receiver,
            amount = 25.0,
            commit = True,
        )

        records = self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].note)
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.model.prompts[0][-1].content, "You have been granted 25.0 credits. Enjoy!")
        self.assertEqual(
            [message["text"] for message in self.api.get_sent_messages(str(chat.external_id))],
            ["Credits granted."],
        )

    def test_credit_grant_rejects_missing_recipient(self):
        recipient_id = UUID("44444444-4444-4444-8444-d44444444444")

        with self.assertRaises(NotFoundError) as context:
            self.service.grant_credits(
                recipient = recipient_id,
                amount = 25.0,
                commit = True,
            )

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)
        self.assertEqual(self.di.user_repo.get(self.agent.id), self.agent)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.agent.id), [])

    def test_credit_grant_rejects_unpersisted_user(self):
        recipient = stubs.domain.user(id = None)

        with self.assertRaises(NotFoundError) as context:
            self.service.grant_credits(
                recipient = recipient,
                amount = 25.0,
                commit = True,
            )

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)
