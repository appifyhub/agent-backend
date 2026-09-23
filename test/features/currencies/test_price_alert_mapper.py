import unittest
from datetime import timedelta
from uuid import uuid4

import stubs

from features.currencies.asset_price import AssetType
from features.currencies.price_alert_mapper import apply_to_db_model, db, domain


class PriceAlertMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.price_alert_db()

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, db_model.chat_id)
        self.assertEqual(result.owner_id, db_model.owner_id)
        self.assertEqual(result.asset_type, AssetType(db_model.asset_type))
        self.assertEqual(result.asset_id, db_model.asset_id)
        self.assertEqual(result.currency, db_model.currency)
        self.assertEqual(result.threshold_percent, db_model.threshold_percent)
        self.assertEqual(result.last_price, db_model.last_price)
        self.assertEqual(result.last_price_time, db_model.last_price_time)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.price_alert()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.owner_id, domain_model.owner_id)
        self.assertEqual(result.asset_type, domain_model.asset_type.value)
        self.assertEqual(result.asset_id, domain_model.asset_id)
        self.assertEqual(result.currency, domain_model.currency)
        self.assertEqual(result.threshold_percent, domain_model.threshold_percent)
        self.assertEqual(result.last_price, domain_model.last_price)
        self.assertEqual(result.last_price_time, domain_model.last_price_time)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = stubs.domain.price_alert()

        result = domain(db(original))

        self.assertEqual(result, original)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.price_alert_db()
        original_chat_id = db_model.chat_id
        original_asset_type = db_model.asset_type
        original_asset_id = db_model.asset_id
        original_currency = db_model.currency
        domain_model = stubs.domain.price_alert(
            chat_id = uuid4(),
            owner_id = uuid4(),
            asset_type = AssetType.fiat,
            asset_id = "GBP",
            currency = "CHF",
            threshold_percent = 10,
            last_price = 1.15,
            last_price_time = db_model.last_price_time + timedelta(days = 1),
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.chat_id, original_chat_id)
        self.assertEqual(db_model.asset_type, original_asset_type)
        self.assertEqual(db_model.asset_id, original_asset_id)
        self.assertEqual(db_model.currency, original_currency)
        self.assertEqual(db_model.owner_id, domain_model.owner_id)
        self.assertEqual(db_model.threshold_percent, domain_model.threshold_percent)
        self.assertEqual(db_model.last_price, domain_model.last_price)
        self.assertEqual(db_model.last_price_time, domain_model.last_price_time)
