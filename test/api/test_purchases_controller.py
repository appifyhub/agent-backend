from datetime import datetime, timezone
from unittest import TestCase
from uuid import UUID, uuid4

import stubs
from util.di_utils import di_for_tests

from api.purchases_controller import PurchasesController
from di.di import DI
from features.users.user import User
from util.error_codes import INVALID_LIMIT, NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class PurchasesControllerTest(TestCase):

    di: DI
    controller: PurchasesController
    user: User
    other: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.other = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None, whatsapp_user_id = None, connect_key = "OTHER-USER",
        ))
        self.di.inject_invoker(self.user)
        self.controller = self.di.purchases_controller

    def test_fetch_purchase_records_success(self):
        record = self.di.purchase_record_repo.save(stubs.domain.purchase_record())

        self.assertEqual(self.controller.fetch_purchase_records(self.user.id.hex), [record])

    def test_fetch_purchase_records_with_pagination(self):
        records = [
            self.di.purchase_record_repo.save(stubs.domain.purchase_record(
                id = uuid4(), sale_id = f"sale-{day}", license_key = f"LICENSE-{day}",
                sale_timestamp = datetime(2026, 1, day, tzinfo = timezone.utc),
            ))
            for day in range(1, 6)
        ]

        result = self.controller.fetch_purchase_records(self.user.id.hex, skip = 2, limit = 2)

        self.assertEqual(result, [records[2], records[1]])

    def test_fetch_purchase_records_with_date_filters(self):
        records = [
            self.di.purchase_record_repo.save(stubs.domain.purchase_record(
                id = uuid4(), sale_id = f"sale-{day}", license_key = f"LICENSE-{day}",
                sale_timestamp = datetime(2026, 1, day, tzinfo = timezone.utc),
            ))
            for day in (1, 15, 31)
        ]

        result = self.controller.fetch_purchase_records(
            self.user.id.hex,
            start_date = datetime(2026, 1, 10, tzinfo = timezone.utc),
            end_date = datetime(2026, 1, 20, tzinfo = timezone.utc),
        )

        self.assertEqual(result, [records[1]])

    def test_fetch_purchase_records_with_product_filter(self):
        record = self.di.purchase_record_repo.save(stubs.domain.purchase_record())
        self.di.purchase_record_repo.save(stubs.domain.purchase_record(
            id = uuid4(), sale_id = "other-sale", license_key = "OTHER-LICENSE", product_id = "other-product",
        ))

        result = self.controller.fetch_purchase_records(self.user.id.hex, product_id = record.product_id)

        self.assertEqual(result, [record])

    def test_fetch_purchase_records_empty_result(self):
        self.assertEqual(self.controller.fetch_purchase_records(self.user.id.hex), [])

    def test_fetch_purchase_records_limit_exceeds_maximum(self):
        with self.assertRaises(ValidationError) as context:
            self.controller.fetch_purchase_records(self.user.id.hex, limit = 101)

        self.assertEqual(context.exception.error_code, INVALID_LIMIT)

    def test_fetch_purchase_records_authorization_failure(self):
        self.di.purchase_record_repo.save(stubs.domain.purchase_record(user_id = self.other.id))

        with self.assertRaises(AuthorizationError) as context:
            self.controller.fetch_purchase_records(self.other.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

    def test_fetch_purchase_aggregates_success(self):
        records = [
            self.di.purchase_record_repo.save(stubs.domain.purchase_record(
                id = uuid4(), sale_id = f"sale-{number}", license_key = f"LICENSE-{number}",
            ))
            for number in range(3)
        ]

        result = self.controller.fetch_purchase_aggregates(self.user.id.hex)

        self.assertEqual(result.total_purchase_count, 3)
        self.assertEqual(result.total_cost_cents, sum(record.price for record in records))
        self.assertEqual(result.total_net_cost_cents, 2550)
        self.assertEqual(result.by_product[records[0].product_id].record_count, 3)
        self.assertEqual([product.id for product in result.all_products_used], [records[0].product_id])

    def test_fetch_purchase_aggregates_with_date_filters(self):
        for day in (1, 15, 31):
            self.di.purchase_record_repo.save(stubs.domain.purchase_record(
                id = uuid4(), sale_id = f"sale-{day}", license_key = f"LICENSE-{day}",
                sale_timestamp = datetime(2026, 1, day, tzinfo = timezone.utc), price = day * 100,
            ))

        result = self.controller.fetch_purchase_aggregates(
            self.user.id.hex,
            start_date = datetime(2026, 1, 10, tzinfo = timezone.utc),
            end_date = datetime(2026, 1, 20, tzinfo = timezone.utc),
        )

        self.assertEqual(result.total_purchase_count, 1)
        self.assertEqual(result.total_cost_cents, 1500)

    def test_fetch_purchase_aggregates_authorization_failure(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.fetch_purchase_aggregates(self.other.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

    def test_fetch_purchase_aggregates_excludes_refunded(self):
        self.di.purchase_record_repo.save(stubs.domain.purchase_record())
        self.di.purchase_record_repo.save(stubs.domain.purchase_record(
            id = uuid4(), sale_id = "refunded-sale", license_key = "REFUNDED-LICENSE", refunded = True,
        ))

        result = self.controller.fetch_purchase_aggregates(self.user.id.hex)

        self.assertEqual(result.total_purchase_count, 1)
        self.assertEqual(result.total_cost_cents, 1000)
        self.assertEqual(result.total_net_cost_cents, 850)

    def test_bind_license_key_success(self):
        record = self.di.purchase_record_repo.save(stubs.domain.purchase_record(user_id = None))

        result = self.controller.bind_license_key(self.user.id.hex, record.license_key)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.license_key, record.license_key)
        self.assertEqual(self.controller.fetch_purchase_records(self.user.id.hex), [result])

    def test_bind_license_key_authorization_failure(self):
        record = self.di.purchase_record_repo.save(stubs.domain.purchase_record(user_id = None))

        with self.assertRaises(AuthorizationError) as context:
            self.controller.bind_license_key(self.other.id.hex, record.license_key)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)
        self.assertEqual(self.di.purchase_service.get_by_user(self.other.id), [])
