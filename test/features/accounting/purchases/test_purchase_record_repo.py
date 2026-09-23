import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import stubs
from db.sql_util import SQLUtil

from features.accounting.purchases.purchase_record_repo import PurchaseRecordRepository
from util.errors import NotFoundError, ValidationError


class PurchaseRecordRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: PurchaseRecordRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.purchase_record_repo()
        self.user = self.sql.user_repo().save(stubs.domain.user())

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_new(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = f"sale-{uuid4().hex[:8]}",
        )
        persisted = self.repo.save(record)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.user_id, self.user.id)
        self.assertEqual(persisted.sale_id, record.sale_id)
        self.assertEqual(persisted.price, record.price)

    def test_save_upserts_by_id(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = f"sale-{uuid4().hex[:8]}",
        )
        persisted = self.repo.save(record)

        persisted.price = 2000
        updated = self.repo.save(persisted)

        self.assertEqual(updated.id, persisted.id)
        self.assertEqual(updated.price, 2000)

    def test_save_upserts_by_sale_id(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-unique-123",
        )
        self.repo.save(record)

        new_record = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-unique-123",
            price = 2000,
        )
        updated = self.repo.save(new_record)

        self.assertEqual(updated.sale_id, "sale-unique-123")
        self.assertEqual(updated.price, 2000)

    def test_get_by_user_pagination_limit(self):
        for _ in range(3):
            self.repo.save(
                stubs.domain.purchase_record(
                    id = uuid4(),
                    user_id = self.user.id,
                    sale_id = f"sale-{uuid4().hex[:8]}",
                ),
            )

        records = self.repo.get_by_user(self.user.id, limit = 2)
        self.assertEqual(len(records), 2)

        records_all = self.repo.get_by_user(self.user.id, limit = 10)
        self.assertEqual(len(records_all), 3)

    def test_get_by_user_pagination_skip(self):
        for _ in range(5):
            self.repo.save(
                stubs.domain.purchase_record(
                    id = uuid4(),
                    user_id = self.user.id,
                    sale_id = f"sale-{uuid4().hex[:8]}",
                ),
            )

        records = self.repo.get_by_user(self.user.id, skip = 2, limit = 10)
        self.assertEqual(len(records), 3)

    def test_get_by_user_start_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now - timedelta(days = 2),
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now,
            ),
        )

        records = self.repo.get_by_user(self.user.id, start_date = now - timedelta(hours = 1))

        self.assertEqual(len(records), 1)

    def test_get_by_user_end_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now - timedelta(days = 2),
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now,
            ),
        )

        records = self.repo.get_by_user(self.user.id, end_date = now - timedelta(days = 1))

        self.assertEqual(len(records), 1)

    def test_get_by_user_date_range_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now - timedelta(days = 5),
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now - timedelta(days = 2),
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now,
            ),
        )

        records = self.repo.get_by_user(
            self.user.id,
            start_date = now - timedelta(days = 3),
            end_date = now - timedelta(days = 1),
        )

        self.assertEqual(len(records), 1)

    def test_get_by_user_product_filter(self):
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-B",
            ),
        )

        records = self.repo.get_by_user(self.user.id, product_id = "product-A")

        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.product_id, "product-A")

    def test_get_aggregates_by_user(self):
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
                price = 500,
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-B",
                price = 2000,
            ),
        )

        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_purchase_count, 3)
        self.assertEqual(stats.total_cost_cents, 3500)
        self.assertEqual(stats.total_net_cost_cents, 3500 - (3 * (100 + 50)))

        self.assertEqual(len(stats.by_product), 2)
        self.assertEqual(stats.by_product["product-A"].record_count, 2)
        self.assertEqual(stats.by_product["product-A"].total_cost_cents, 1500)
        self.assertEqual(stats.by_product["product-B"].record_count, 1)
        self.assertEqual(stats.by_product["product-B"].total_cost_cents, 2000)

        product_ids = [p.id for p in stats.all_products_used]
        self.assertIn("product-A", product_ids)
        self.assertIn("product-B", product_ids)

    def test_get_aggregates_by_user_empty(self):
        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_purchase_count, 0)
        self.assertEqual(stats.total_cost_cents, 0)
        self.assertEqual(stats.total_net_cost_cents, 0)
        self.assertEqual(len(stats.by_product), 0)
        self.assertEqual(len(stats.all_products_used), 0)

    def test_get_aggregates_by_user_with_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now - timedelta(days = 5),
                price = 10000,
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                sale_timestamp = now,
            ),
        )

        stats = self.repo.get_aggregates_by_user(
            self.user.id,
            start_date = now - timedelta(hours = 1),
        )

        self.assertEqual(stats.total_purchase_count, 1)
        self.assertEqual(stats.total_cost_cents, 1000)

    def test_get_aggregates_by_user_with_product_filter_keeps_all_products_list(self):
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-B",
                price = 2000,
            ),
        )

        stats = self.repo.get_aggregates_by_user(self.user.id, product_id = "product-A")

        self.assertEqual(stats.total_purchase_count, 1)
        self.assertEqual(stats.total_cost_cents, 1000)
        self.assertEqual(len(stats.by_product), 1)
        self.assertIn("product-A", stats.by_product)

        product_ids = [p.id for p in stats.all_products_used]
        self.assertEqual(len(product_ids), 2)
        self.assertIn("product-A", product_ids)
        self.assertIn("product-B", product_ids)

    def test_get_aggregates_by_user_excludes_refunded_purchases(self):
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
                price = 500,
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-A",
                price = 3000,
                refunded = True,
            ),
        )
        self.repo.save(
            stubs.domain.purchase_record(
                id = uuid4(),
                user_id = self.user.id,
                sale_id = f"sale-{uuid4().hex[:8]}",
                product_id = "product-B",
                price = 2000,
                refunded = True,
            ),
        )

        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_purchase_count, 2)
        self.assertEqual(stats.total_cost_cents, 1500)
        self.assertEqual(stats.total_net_cost_cents, 1500 - (2 * (100 + 50)))

        self.assertEqual(len(stats.by_product), 1)
        self.assertIn("product-A", stats.by_product)
        self.assertEqual(stats.by_product["product-A"].record_count, 2)
        self.assertEqual(stats.by_product["product-A"].total_cost_cents, 1500)

        self.assertEqual(len(stats.all_products_used), 1)
        product_ids = [p.id for p in stats.all_products_used]
        self.assertIn("product-A", product_ids)
        self.assertNotIn("product-B", product_ids)

    def test_bind_license_key_to_user_success(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            sale_id = f"sale-{uuid4().hex[:8]}",
            user_id = None,
            license_key = "LICENSE-123",
        )
        self.repo.save(record)

        bound = self.repo.bind_license_key_to_user("LICENSE-123", self.user.id)

        self.assertEqual(bound.license_key, "LICENSE-123")
        self.assertEqual(bound.user_id, self.user.id)

    def test_bind_license_key_to_user_not_found(self):
        with self.assertRaises(NotFoundError) as context:
            self.repo.bind_license_key_to_user("NONEXISTENT", self.user.id)

        self.assertIn("not found", str(context.exception))

    def test_bind_license_key_to_user_refunded(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            sale_id = f"sale-{uuid4().hex[:8]}",
            user_id = None,
            license_key = "LICENSE-REF",
            refunded = True,
        )
        self.repo.save(record)

        with self.assertRaises(ValidationError) as context:
            self.repo.bind_license_key_to_user("LICENSE-REF", self.user.id)

        self.assertIn("refunded", str(context.exception))

    def test_bind_license_key_to_user_already_bound(self):
        other_user = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654321,
                whatsapp_user_id = "whatsapp-other",
                connect_key = "OTHER-KEY",
            ),
        )
        record = stubs.domain.purchase_record(
            id = uuid4(),
            sale_id = f"sale-{uuid4().hex[:8]}",
            user_id = other_user.id,
            license_key = "LICENSE-BOUND",
        )
        self.repo.save(record)

        with self.assertRaises(ValidationError) as context:
            self.repo.bind_license_key_to_user("LICENSE-BOUND", self.user.id)

        self.assertIn("already bound", str(context.exception))

    def test_bind_license_key_to_user_test_order(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            sale_id = f"sale-{uuid4().hex[:8]}",
            user_id = None,
            license_key = "LICENSE-TEST",
            test = True,
        )
        self.repo.save(record)

        with self.assertRaises(ValidationError) as context:
            self.repo.bind_license_key_to_user("LICENSE-TEST", self.user.id)

        self.assertIn("test order", str(context.exception))

    def test_bind_license_key_to_user_preorder(self):
        record = stubs.domain.purchase_record(
            id = uuid4(),
            sale_id = f"sale-{uuid4().hex[:8]}",
            user_id = None,
            license_key = "LICENSE-PREORDER",
            is_preorder_authorization = True,
        )
        self.repo.save(record)

        with self.assertRaises(ValidationError) as context:
            self.repo.bind_license_key_to_user("LICENSE-PREORDER", self.user.id)

        self.assertIn("preorder", str(context.exception))

    def test_save_preserves_user_id_when_update_has_none(self):
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-user",
            license_key = "LICENSE-ORIG",
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = None,
            sale_id = "sale-preserve-user",
            refunded = True,
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.user_id, self.user.id)
        self.assertTrue(updated.refunded)

    def test_save_preserves_license_key_when_update_has_none(self):
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-license",
            license_key = "LICENSE-PRESERVED",
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-license",
            license_key = None,
            refunded = True,
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.license_key, "LICENSE-PRESERVED")
        self.assertTrue(updated.refunded)

    def test_save_preserves_url_params_when_update_has_none(self):
        original_params = {"user_id": str(self.user.id), "source": "website"}
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-params",
            license_key = "LICENSE-URL",
            url_params = original_params,
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-params",
            license_key = "LICENSE-URL",
            url_params = None,
            refunded = True,
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.url_params, original_params)
        self.assertTrue(updated.refunded)

    def test_save_preserves_custom_fields_when_update_has_none(self):
        original_fields = {"notes": "special order", "priority": "high"}
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-custom",
            license_key = "LICENSE-CUSTOM",
            custom_fields = original_fields,
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-preserve-custom",
            license_key = "LICENSE-CUSTOM",
            custom_fields = None,
            refunded = True,
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.custom_fields, original_fields)
        self.assertTrue(updated.refunded)

    def test_save_updates_user_id_when_update_has_value(self):
        other_user = self.sql.user_repo().save(
            stubs.domain.user(
                id = uuid4(),
                telegram_user_id = 987654321,
                whatsapp_user_id = "whatsapp-update",
                connect_key = "UPDATE-KEY",
            ),
        )
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-update-user",
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = other_user.id,
            sale_id = "sale-update-user",
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.user_id, other_user.id)

    def test_save_updates_license_key_when_update_has_value(self):
        original = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-update-license",
            license_key = "LICENSE-OLD",
        )
        self.repo.save(original)

        update = stubs.domain.purchase_record(
            id = uuid4(),
            user_id = self.user.id,
            sale_id = "sale-update-license",
            license_key = "LICENSE-NEW",
        )
        updated = self.repo.save(update)

        self.assertEqual(updated.license_key, "LICENSE-NEW")
