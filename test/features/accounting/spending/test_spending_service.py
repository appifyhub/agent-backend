from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

import stubs
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.usage_record import UsageRecord
from features.chat.config.chat_config import ChatConfig
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import WHATSAPP_MESSAGE_DELIVERY
from features.integrations.integrations import resolve_agent_user
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, USER_NOT_FOUND
from util.errors import NotFoundError, ValidationError


class SpendingServiceValidatePreFlightTest(TestCase):

    di: DI
    service: SpendingService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.spending_service
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_does_nothing_when_not_using_credits(self):
        tool = stubs.domain.configured_tool()

        self.assertIsNone(self.service.validate_pre_flight(tool, input_text = "a" * 4000))

    def test_passes_when_balance_is_sufficient(self):
        user = self.di.user_repo.save(stubs.domain.user())
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.assertIsNone(self.service.validate_pre_flight(tool, max_output_tokens = 0))

        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_raises_when_user_not_found(self):
        tool = stubs.domain.configured_tool(uses_credits = True)

        with self.assertRaises(NotFoundError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)

    def test_raises_when_balance_is_negative(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = -10.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("Insufficient credits", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_raises_when_balance_is_insufficient(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 0.5))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("Insufficient credits", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_uses_video_size_and_duration_in_cost_estimate(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 15.5))
        tool = stubs.domain.configured_tool(
            uses_credits = True,
            payer_id = user.id,
            definition = stubs.domain.external_tool(
                cost_estimate = stubs.domain.cost_estimate(
                    output_video_2k_second = 3,
                    api_call = None,
                    web_search_query = None,
                ),
            ),
        )

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(
                tool,
                input_text = "",
                max_output_tokens = 0,
                output_video_size = "2K",
                output_video_duration_seconds = 5,
            )

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("minimum required 16.0", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)


class SpendingServiceDeductTest(TestCase):

    di: DI
    service: SpendingService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.spending_service

    def test_does_nothing_when_not_using_credits(self):
        user = self.di.user_repo.save(stubs.domain.user())
        tool = stubs.domain.configured_tool(payer_id = user.id)

        self.service.deduct(tool, 10.0)

        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_deduct_reduces_balance(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 50.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.service.deduct(tool, 10.0)

        self.assertEqual(self.di.user_repo.get(user.id), replace(user, credit_balance = 40.0))

    def test_deduct_allows_negative_balance(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 5.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.service.deduct(tool, 50.0)

        self.assertEqual(self.di.user_repo.get(user.id), replace(user, credit_balance = -45.0))


class SpendingServiceDeliveryTest(TestCase):

    di: DI
    service: SpendingService
    payer: User
    recipient: User
    chat: ChatConfig
    record: UsageRecord

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.spending_service
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "platform-pricing.yaml"
        path.write_text("""\
platforms:
  telegram:
    markets:
      global: {default: true, categories: {service: "0"}}
  whatsapp:
    markets:
      global: {default: true, categories: {service: "0.7"}}
      uk: {prefixes: ["44"], categories: {service: "1.1"}}
""")
        self.addCleanup(
            setattr,
            config,
            "integration_delivery_pricing_config_path",
            config.integration_delivery_pricing_config_path,
        )
        config.integration_delivery_pricing_config_path = str(path)
        self.recipient = self.di.user_repo.save(
            stubs.domain.user(whatsapp_user_id = "5511999999999", credit_balance = 0),
        )
        self.payer = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654320,
                whatsapp_user_id = "447700900111",
                connect_key = "SENDER-KEY",
                credit_balance = 10.0,
            ),
        )
        self.chat = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = self.recipient.whatsapp_user_id,
            ),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = self.recipient.id, chat_id = self.chat.chat_id),
        )
        self.record = stubs.domain.usage_record(
            user_id = self.payer.id,
            payer_id = self.payer.id,
            counterpart_id = self.recipient.id,
            chat_id = self.chat.chat_id,
            tool = WHATSAPP_MESSAGE_DELIVERY,
            tool_purpose = ToolType.message_delivery,
            model_cost_credits = 0.5,
            remote_runtime_cost_credits = 0.3,
            api_call_cost_credits = 0.4,
            maintenance_fee_credits = 0.2,
            total_cost_credits = 1.4,
        )

    def _save_agent_membership(self, chat: ChatConfig) -> User:
        agent = self.di.user_repo.save(
            replace(
                resolve_agent_user(chat.chat_type),
                id = uuid4(),
                connect_key = f"AGENT-{uuid4().hex[:8]}",
            ),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = agent.id, chat_id = chat.chat_id),
        )
        return agent

    def test_delivery_pre_flight_rejects_unfunded_private_payer(self):
        payer = self.di.user_repo.save(replace(self.payer, credit_balance = 1.0))
        chat = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = payer.whatsapp_user_id,
                is_private = True,
            ),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = payer.id, chat_id = chat.chat_id),
        )
        self._save_agent_membership(chat)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_message_delivery_pre_flight(chat, payer.id)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("minimum required 1.1", str(context.exception))
        self.assertEqual(self.di.user_repo.get(payer.id), payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(payer.id), [])

    def test_delivery_pre_flight_is_stateless_and_does_not_charge(self):
        chat = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = self.payer.whatsapp_user_id,
                is_private = True,
            ),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = self.payer.id, chat_id = chat.chat_id),
        )
        self._save_agent_membership(chat)

        self.service.validate_message_delivery_pre_flight(chat, self.payer.id)

        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.payer.id), [])

        payer = self.di.user_repo.save(replace(self.payer, credit_balance = 0.0))
        with self.assertRaises(ValidationError) as context:
            self.service.validate_message_delivery_pre_flight(chat, payer.id)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.di.user_repo.get(payer.id), payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(payer.id), [])

    def test_delivery_pre_flight_requires_full_group_recipient_total(self):
        payer = self.di.user_repo.save(replace(self.payer, credit_balance = 1.2))
        other_recipient = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654321,
                whatsapp_user_id = "447700900123",
                connect_key = "PREFLIGHT-RECIPIENT",
                credit_balance = 0,
            ),
        )
        group = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = "preflight-group",
                is_private = False,
            ),
        )
        for recipient in (payer, self.recipient, other_recipient):
            self.di.chat_membership_repo.save(
                stubs.domain.chat_membership(user_id = recipient.id, chat_id = group.chat_id),
            )
        self._save_agent_membership(group)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_message_delivery_pre_flight(group, payer.id)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("minimum required 2.9", str(context.exception))

        payer = self.di.user_repo.save(replace(payer, credit_balance = 3.0))
        self.service.validate_message_delivery_pre_flight(group, payer.id)

        self.assertEqual(self.di.user_repo.get(payer.id), payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(payer.id), [])

    def test_delivery_pre_flight_allows_free_telegram_with_negative_balance(self):
        payer = self.di.user_repo.save(replace(self.payer, credit_balance = -1.0))
        chat = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.telegram,
                external_id = payer.telegram_chat_id,
                is_private = True,
            ),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = payer.id, chat_id = chat.chat_id),
        )
        self._save_agent_membership(chat)

        self.service.validate_message_delivery_pre_flight(chat, payer.id)

        self.assertEqual(self.di.user_repo.get(payer.id), payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(payer.id), [])

    def test_paid_delivery_charges_payer_at_recipient_rate_without_maintenance_fee(self):
        invoker = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654321,
                whatsapp_user_id = "invoker-whatsapp",
                connect_key = "INVOKER-KEY",
                credit_balance = 20.0,
            ),
        )
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 2.0

        self.di.clone(invoker_id = str(invoker.id)).spending_service.charge_for_message_delivery(self.chat, self.payer.id)

        with self.di.new_session() as db:
            fresh_di = self.di.clone(db = db)
            records = fresh_di.usage_record_repo.get_by_user(self.payer.id)
            self.assertEqual([record.tool_purpose for record in records], [ToolType.message_delivery])
            record = records[0]
            self.assertEqual(record.user_id, self.payer.id)
            self.assertEqual(record.payer_id, self.payer.id)
            self.assertEqual(record.counterpart_id, self.recipient.id)
            self.assertEqual(record.tool.provider.id, "meta")
            self.assertEqual(record.api_call_cost_credits, 0.7)
            self.assertEqual(record.total_cost_credits, 0.7)
            self.assertFalse(record.is_delivery_reconciled)
            self.assertAlmostEqual(fresh_di.user_repo.get(self.payer.id).credit_balance, 9.3)
            self.assertEqual(fresh_di.user_repo.get(self.recipient.id), self.recipient)
            self.assertEqual(fresh_di.user_repo.get(invoker.id), invoker)

    def test_free_delivery_has_no_charge_or_usage_record(self):
        chat = stubs.domain.chat_config(
            chat_type = ChatConfigDB.ChatType.telegram,
            external_id = str(self.recipient.telegram_user_id),
        )

        self.service.charge_for_message_delivery(chat, self.payer.id)

        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.payer.id), [])

    def test_paid_delivery_for_unknown_payer_fails_without_recording_a_charge(self):
        payer = stubs.domain.user(id = uuid4())

        with self.assertRaises(NotFoundError) as context:
            self.service.charge_for_message_delivery(self.chat, payer.id)

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.payer.id), [])

    def test_free_delivery_refunds_api_cost_only_and_cannot_refund_twice(self):
        self.di.usage_record_repo.create(self.record)

        self.service.reconcile_message_delivery(
            self.chat,
            self.recipient,
            is_delivery_free = True,
        )
        self.service.reconcile_message_delivery(
            self.chat,
            self.recipient,
            is_delivery_free = True,
        )

        record = self.di.usage_record_repo.get_by_user(self.payer.id)[0]
        self.assertAlmostEqual(self.di.user_repo.get(self.payer.id).credit_balance, 10.4)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(record.api_call_cost_credits, 0)
        self.assertAlmostEqual(record.total_cost_credits, 1.0)
        self.assertTrue(record.is_delivery_reconciled)

    def test_paid_receipt_preserves_recorded_cost_and_balance(self):
        self.di.usage_record_repo.create(self.record)
        config.integration_delivery_pricing_config_path += ".missing"

        self.service.reconcile_message_delivery(self.chat, self.recipient, is_delivery_free = False)

        record = self.di.usage_record_repo.get_by_user(self.payer.id)[0]
        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(record.api_call_cost_credits, 0.4)
        self.assertAlmostEqual(record.total_cost_credits, 1.4)
        self.assertTrue(record.is_delivery_reconciled)

    def test_unmatched_paid_receipt_does_not_change_any_records(self):
        reconciled = self.service.reconcile_message_delivery(self.chat, self.recipient, is_delivery_free = False)

        self.assertFalse(reconciled)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.payer.id), [])

    def test_group_delivery_prices_and_reconciliation_are_individual_to_each_recipient(self):
        other_recipient = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654321,
                whatsapp_user_id = "447700900123",
                connect_key = "OTHER-RECIPIENT",
                credit_balance = 0,
            ),
        )
        bot = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = None,
                whatsapp_user_id = resolve_agent_user(ChatConfigDB.ChatType.whatsapp).whatsapp_user_id,
                connect_key = "BOT-MEMBER",
                credit_balance = 20.0,
            ),
        )
        group = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = "shared-group",
                is_private = False,
            ),
        )

        for recipient in (self.payer, self.recipient, other_recipient, bot):
            self.di.chat_membership_repo.save(
                stubs.domain.chat_membership(user_id = recipient.id, chat_id = group.chat_id),
            )

        self.service.charge_for_message_delivery(group, self.payer.id)

        self.assertAlmostEqual(self.di.user_repo.get(self.payer.id).credit_balance, 7.1)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(self.di.user_repo.get(other_recipient.id), other_recipient)
        self.assertEqual(self.di.user_repo.get(bot.id), bot)

        self.service.reconcile_message_delivery(group, self.recipient, is_delivery_free = True)

        self.assertAlmostEqual(self.di.user_repo.get(self.payer.id).credit_balance, 7.8)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        self.assertEqual(self.di.user_repo.get(other_recipient.id), other_recipient)
        self.assertEqual(self.di.user_repo.get(bot.id), bot)
        records = {record.counterpart_id: record for record in self.di.usage_record_repo.get_by_user(self.payer.id)}
        record = records[self.recipient.id]
        other_record = records[other_recipient.id]
        self.assertEqual(record.api_call_cost_credits, 0)
        self.assertTrue(record.is_delivery_reconciled)
        self.assertEqual(other_record.api_call_cost_credits, 1.1)
        self.assertFalse(other_record.is_delivery_reconciled)
        self.assertEqual(records[self.payer.id].api_call_cost_credits, 1.1)
        self.assertFalse(records[self.payer.id].is_delivery_reconciled)

    def test_private_reply_bills_payer_recipient_but_not_the_agent(self):
        bot = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = None,
                whatsapp_user_id = resolve_agent_user(ChatConfigDB.ChatType.whatsapp).whatsapp_user_id,
                connect_key = "PRIVATE-BOT-MEMBER",
                credit_balance = 20.0,
            ),
        )
        chat = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = self.payer.whatsapp_user_id,
                is_private = True,
            ),
        )
        for recipient in (self.payer, bot):
            self.di.chat_membership_repo.save(
                stubs.domain.chat_membership(user_id = recipient.id, chat_id = chat.chat_id),
            )

        self.service.charge_for_message_delivery(chat, self.payer.id)

        self.assertAlmostEqual(self.di.user_repo.get(self.payer.id).credit_balance, 8.9)
        self.assertEqual(self.di.user_repo.get(bot.id), bot)
        records = self.di.usage_record_repo.get_by_user(self.payer.id)
        self.assertEqual(
            [(record.counterpart_id, record.api_call_cost_credits) for record in records],
            [(self.payer.id, 1.1)],
        )

        self.service.reconcile_message_delivery(chat, self.payer, is_delivery_free = True)

        records = self.di.usage_record_repo.get_by_user(self.payer.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(self.di.user_repo.get(self.payer.id), self.payer)
        self.assertEqual(records[0].api_call_cost_credits, 0.0)
        self.assertEqual(records[0].total_cost_credits, 0.0)
        self.assertFalse(records[0].is_failed)
        self.assertTrue(records[0].is_delivery_reconciled)

    def test_group_reply_bills_payer_and_other_recipient_but_not_the_agent(self):
        bot = self.di.user_repo.save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = None,
                whatsapp_user_id = resolve_agent_user(ChatConfigDB.ChatType.whatsapp).whatsapp_user_id,
                connect_key = "SINGLE-RECIPIENT-BOT",
                credit_balance = 20.0,
            ),
        )
        group = self.di.chat_config_repo.save(
            stubs.domain.chat_config(
                chat_id = uuid4(),
                chat_type = ChatConfigDB.ChatType.whatsapp,
                external_id = "one-recipient-group",
                is_private = False,
            ),
        )
        for recipient in (self.payer, bot, self.recipient):
            self.di.chat_membership_repo.save(
                stubs.domain.chat_membership(user_id = recipient.id, chat_id = group.chat_id),
            )

        self.service.charge_for_message_delivery(group, self.payer.id)

        self.assertAlmostEqual(self.di.user_repo.get(self.payer.id).credit_balance, 8.2)
        self.assertEqual(self.di.user_repo.get(bot.id), bot)
        self.assertEqual(self.di.user_repo.get(self.recipient.id), self.recipient)
        records = self.di.usage_record_repo.get_by_user(self.payer.id)
        self.assertEqual(
            {record.counterpart_id: record.api_call_cost_credits for record in records},
            {self.payer.id: 1.1, self.recipient.id: 0.7},
        )
