from unittest import TestCase
from uuid import UUID

import stubs
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.purchases.purchase_service import PurchaseService
from features.users.user import User
from util.config import config

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
