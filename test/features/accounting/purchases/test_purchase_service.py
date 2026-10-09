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
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.purchases.purchase_service import PurchaseService
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integration_config import THE_AGENT
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS
from util.errors import ValidationError

KNOWN_PRODUCT_ID = "GUMROAD_ID_100"


class PurchaseServiceTest(TestCase):

    di: DI
    service: PurchaseService
    user: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.service = self.di.purchase_service
        self.addCleanup(setattr, config, "products", config.products)
        config.products = {KNOWN_PRODUCT_ID: stubs.domain.configured_product(id = KNOWN_PRODUCT_ID)}

    def test_record_purchase_success(self):
        payload = stubs.api.gumroad_ping_payload(
            sale_id = "sale-123",
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
        )

        record = self.service.record_purchase(payload)

        self.assertIsInstance(record, PurchaseRecord)
        self.assertEqual(record.sale_id, "sale-123")
        self.assertEqual(record.price, payload.price)

    def test_record_purchase_ignores_unknown_product(self):
        unknown_product_id = "UNKNOWN_PRODUCT"
        payload = stubs.api.gumroad_ping_payload(product_id = unknown_product_id)

        record = self.service.record_purchase(payload)

        self.assertIsNone(record)
        self.assertEqual(self.service.get_by_user(self.user.id), [])

    def test_record_purchase_extracts_user_id_from_url_params(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
        )

        record = self.service.record_purchase(payload)

        assert record is not None
        self.assertEqual(record.user_id, self.user.id)

    def test_record_purchase_handles_missing_user_id(self):
        payload = stubs.api.gumroad_ping_payload(product_id = KNOWN_PRODUCT_ID, url_params = None)

        record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_handles_invalid_user_id(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": "invalid-uuid"},
        )

        record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_handles_nonexistent_user(self):
        missing_user_id = UUID("44444444-4444-4444-8444-d44444444444")
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(missing_user_id)},
        )

        record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_persists_to_repo(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
        )

        record = self.service.record_purchase(payload)

        self.assertEqual(self.service.get_by_user(self.user.id), [record])

    def test_record_purchase_allocates_credits_on_new_purchase(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
            quantity = 2,
        )

        self.service.record_purchase(payload)

        self.assertEqual(self.di.user_repo.get(self.user.id).credit_balance, self.user.credit_balance + 200)

    def test_record_purchase_notifies_resolved_chat(self):
        self.di.user_repo.save(stubs.domain.user(
            id = THE_AGENT.id,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
            connect_key = "PURCHASE-AGENT",
        ))
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.user.telegram_chat_id))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = self.user.id, chat_id = chat.chat_id))
        agent_di = self.di.clone(invoker_id = THE_AGENT.id.hex)
        tool = agent_di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        model = cast(FakeChatModel, agent_di.base_chat_langchain_model(tool))
        model.responses.append(stubs.external.ai_message(content = "Purchase confirmed."))
        api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
        )

        self.service.record_purchase(payload)

        self.assertEqual(len(model.prompts), 1)
        self.assertEqual(
            [message["text"] for message in api.get_sent_messages(str(chat.external_id))],
            ["Purchase confirmed."],
        )

    def test_record_purchase_logs_error_and_preserves_purchase_when_delivery_cannot_be_funded(self):
        self.di.user_repo.save(stubs.domain.user(
            id = THE_AGENT.id,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
            connect_key = "PURCHASE-AGENT",
        ))
        user = self.di.user_repo.save(replace(
            self.user,
            credit_balance = -100.0,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = user.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = user.id, chat_id = chat.chat_id))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = user.id,
            message_id = "purchase-message",
            sent_at = datetime.now(),
        ))
        agent_di = self.di.clone(invoker_id = THE_AGENT.id.hex)
        tool = agent_di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        model = cast(FakeChatModel, agent_di.base_chat_langchain_model(tool))
        api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(user.id)},
        )

        with patch("features.accounting.purchases.purchase_service.log.e") as error_log:
            record = self.service.record_purchase(payload)

        assert record is not None
        self.assertEqual(self.service.get_by_user(user.id), [record])
        self.assertEqual(self.di.user_repo.get(user.id).credit_balance, 0.0)
        self.assertEqual(len(model.prompts), 0)
        self.assertEqual(api.get_sent_messages(str(chat.external_id)), [])
        error_log.assert_called_once()
        self.assertEqual(error_log.call_args.args[0], f"Failed to send purchase notification to user {user.id.hex}")
        notification_error = error_log.call_args.args[1]
        self.assertIsInstance(notification_error, ValidationError)
        self.assertEqual(notification_error.error_code, INSUFFICIENT_CREDITS)

    def test_record_purchase_does_not_allocate_credits_for_donation(self):
        donation_product_id = "GUMROAD_ID_DONATION"
        payload = stubs.api.gumroad_ping_payload(
            product_id = donation_product_id,
            url_params = {"user_id": str(self.user.id)},
        )

        config.products[donation_product_id] = stubs.domain.configured_product(id = donation_product_id, credits = 0)
        record = self.service.record_purchase(payload)

        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)
        assert record is not None

    def test_record_purchase_does_not_allocate_credits_for_test_purchase(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
            test = True,
        )

        self.service.record_purchase(payload)

        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_record_purchase_does_not_allocate_credits_without_user_id(self):
        payload = stubs.api.gumroad_ping_payload(product_id = KNOWN_PRODUCT_ID)

        self.service.record_purchase(payload)

        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_record_purchase_deducts_credits_on_refund(self):
        payload = stubs.api.gumroad_ping_payload(
            product_id = KNOWN_PRODUCT_ID,
            url_params = {"user_id": str(self.user.id)},
        )
        purchased = self.service.record_purchase(payload)
        self.assertEqual(self.di.user_repo.get(self.user.id).credit_balance, self.user.credit_balance + 100)

        refunded = self.service.record_purchase(payload.model_copy(update = {"refunded": True}))

        self.assertEqual(refunded.id, purchased.id)
        self.assertTrue(refunded.refunded)
        self.assertEqual(self.service.get_by_user(self.user.id), [refunded])
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)

    def test_bind_license_key_allocates_credits(self):
        purchase = self.di.purchase_record_repo.save(stubs.domain.purchase_record(
            user_id = None,
            product_id = KNOWN_PRODUCT_ID,
        ))

        bound = self.service.bind_license_key(self.user.id, purchase.license_key)

        self.assertEqual(bound.user_id, self.user.id)
        self.assertEqual(bound.license_key, purchase.license_key)
        self.assertEqual(self.service.get_by_user(self.user.id), [bound])
        self.assertEqual(self.di.user_repo.get(self.user.id).credit_balance, self.user.credit_balance + 100)

    def test_get_by_user_returns_purchases(self):
        purchase = self.di.purchase_record_repo.save(stubs.domain.purchase_record())

        self.assertEqual(self.service.get_by_user(self.user.id), [purchase])

    def test_get_aggregates_by_user_returns_purchase_totals(self):
        purchase = self.di.purchase_record_repo.save(stubs.domain.purchase_record())

        totals = self.service.get_aggregates_by_user(self.user.id)

        self.assertEqual(totals.total_purchase_count, 1)
        self.assertEqual(totals.total_cost_cents, purchase.price)
        self.assertEqual(totals.total_net_cost_cents, purchase.price - purchase.gumroad_fee - purchase.affiliate_credit_amount_cents)  # ruff: ignore[line-too-long]
        self.assertEqual(totals.by_product[purchase.product_id].record_count, 1)
