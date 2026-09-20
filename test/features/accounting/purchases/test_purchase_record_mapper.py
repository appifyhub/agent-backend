import unittest

import stubs

from db.model.purchase_record import PurchaseRecordDB
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.purchases.purchase_record_mapper import db, domain


class PurchaseRecordMapperTest(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None

    def test_domain_to_db_none(self):
        db_obj = db(None)
        self.assertIsNone(db_obj)

    def test_domain_to_db(self):
        domain_record = stubs.domain.purchase_record(
            url_params = {"user_id": "test-user"},
            custom_fields = {"field1": "value1"},
        )
        db_obj = db(domain_record)

        self.assertIsInstance(db_obj, PurchaseRecordDB)
        self.assertEqual(db_obj.id, domain_record.id)
        self.assertEqual(db_obj.user_id, domain_record.user_id)
        self.assertEqual(db_obj.seller_id, domain_record.seller_id)
        self.assertEqual(db_obj.sale_id, domain_record.sale_id)
        self.assertEqual(db_obj.sale_timestamp, domain_record.sale_timestamp)
        self.assertEqual(db_obj.price, domain_record.price)
        self.assertEqual(db_obj.product_id, domain_record.product_id)
        self.assertEqual(db_obj.product_name, domain_record.product_name)
        self.assertEqual(db_obj.product_permalink, domain_record.product_permalink)
        self.assertEqual(db_obj.short_product_id, domain_record.short_product_id)
        self.assertEqual(db_obj.license_key, domain_record.license_key)
        self.assertEqual(db_obj.quantity, domain_record.quantity)
        self.assertEqual(db_obj.gumroad_fee, domain_record.gumroad_fee)
        self.assertEqual(db_obj.affiliate_credit_amount_cents, domain_record.affiliate_credit_amount_cents)
        self.assertEqual(db_obj.discover_fee_charge, domain_record.discover_fee_charge)
        self.assertEqual(db_obj.url_params, domain_record.url_params)
        self.assertEqual(db_obj.custom_fields, domain_record.custom_fields)
        self.assertEqual(db_obj.test, domain_record.test)
        self.assertEqual(db_obj.is_preorder_authorization, domain_record.is_preorder_authorization)
        self.assertEqual(db_obj.refunded, domain_record.refunded)

    def test_db_to_domain(self):
        db_record = stubs.db.purchase_record_db(
            url_params = {"user_id": "test-user"},
            custom_fields = {"field1": "value1"},
        )
        domain_obj = domain(db_record)

        self.assertIsInstance(domain_obj, PurchaseRecord)
        self.assertEqual(domain_obj.id, db_record.id)
        self.assertEqual(domain_obj.user_id, db_record.user_id)
        self.assertEqual(domain_obj.seller_id, db_record.seller_id)
        self.assertEqual(domain_obj.sale_id, db_record.sale_id)
        self.assertEqual(domain_obj.sale_timestamp, db_record.sale_timestamp)
        self.assertEqual(domain_obj.price, db_record.price)
        self.assertEqual(domain_obj.product_id, db_record.product_id)
        self.assertEqual(domain_obj.product_name, db_record.product_name)
        self.assertEqual(domain_obj.product_permalink, db_record.product_permalink)
        self.assertEqual(domain_obj.short_product_id, db_record.short_product_id)
        self.assertEqual(domain_obj.license_key, db_record.license_key)
        self.assertEqual(domain_obj.quantity, db_record.quantity)
        self.assertEqual(domain_obj.gumroad_fee, db_record.gumroad_fee)
        self.assertEqual(domain_obj.affiliate_credit_amount_cents, db_record.affiliate_credit_amount_cents)
        self.assertEqual(domain_obj.discover_fee_charge, db_record.discover_fee_charge)
        self.assertEqual(domain_obj.url_params, db_record.url_params)
        self.assertEqual(domain_obj.custom_fields, db_record.custom_fields)
        self.assertEqual(domain_obj.test, db_record.test)
        self.assertEqual(domain_obj.is_preorder_authorization, db_record.is_preorder_authorization)
        self.assertEqual(domain_obj.refunded, db_record.refunded)

    def test_db_to_domain_none(self):
        domain_obj = domain(None)
        self.assertIsNone(domain_obj)
