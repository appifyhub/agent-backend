import json
from unittest import TestCase
from uuid import UUID

import stubs
from util.di_utils import di_for_tests

from di.di import DI


class LLMToolLibraryConfirmationTest(TestCase):

    di: DI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        sender = self.di.user_repo.save(stubs.domain.user(credit_balance = 100.0))
        recipient = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_username = "recipient",
            telegram_user_id = 987654321,
            telegram_chat_id = "987654321",
            whatsapp_user_id = None,
            connect_key = "RECIPIENT-KEY",
        ))
        self.di.inject_invoker(sender)
        self.di.inject_invoker_chat(stubs.domain.chat_config())
        self.di.chat_membership_service.save(stubs.domain.chat_membership(user_id = sender.id))
        self.sender_id = sender.id
        self.recipient_handle = recipient.telegram_username

    def test_transfer_first_call_returns_proposal_and_no_balance_change(self):
        args = {"recipient_handle": "recipient", "amount": "10.0"}

        result = self.di.llm_tool_library.invoke("transfer_credits_to_user", args)

        data = json.loads(result)
        self.assertEqual(data["result"], "Pending")
        self.assertIn("confirm", data["information"].lower())
        self.assertEqual(self.di.user_repo.get(self.sender_id).credit_balance, 100.0)

    def test_transfer_matching_confirmation_executes(self):
        args = {"recipient_handle": "recipient", "amount": "10.0"}
        self.di.llm_tool_library.invoke("transfer_credits_to_user", args)

        result = self.di.llm_tool_library.invoke("transfer_credits_to_user", args)

        data = json.loads(result)
        self.assertNotEqual(data["result"], "Pending")
        self.assertLess(self.di.user_repo.get(self.sender_id).credit_balance, 100.0)

    def test_transfer_mismatched_confirmation_returns_new_proposal(self):
        args = {"recipient_handle": "recipient", "amount": "10.0"}
        self.di.llm_tool_library.invoke("transfer_credits_to_user", args)
        different_args = {"recipient_handle": "recipient", "amount": "99.0"}

        result = self.di.llm_tool_library.invoke("transfer_credits_to_user", different_args)

        data = json.loads(result)
        self.assertEqual(data["result"], "Pending")
        self.assertEqual(self.di.user_repo.get(self.sender_id).credit_balance, 100.0)
