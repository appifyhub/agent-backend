import unittest
from datetime import datetime
from uuid import UUID

from db.model.price_alert import PriceAlertDB
from features.currencies.asset_price import AssetType
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_mapper import apply_to_db_model, db, domain


class PriceAlertMapperTest(unittest.TestCase):

    chat_id: UUID
    owner_id: UUID
    last_price_time: datetime

    def setUp(self):
        self.chat_id = UUID("11111111-1111-1111-1111-111111111111")
        self.owner_id = UUID("22222222-2222-2222-2222-222222222222")
        self.last_price_time = datetime(2026, 1, 1, 12, 0, 0)

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = PriceAlertDB(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            asset_type = AssetType.fiat.value,
            asset_id = "USD",
            currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.owner_id, self.owner_id)
        self.assertEqual(result.asset_type, AssetType.fiat)
        self.assertEqual(result.asset_id, "USD")
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.threshold_percent, 5)
        self.assertEqual(result.last_price, 0.85)
        self.assertEqual(result.last_price_time, self.last_price_time)

    def test_db_maps_all_fields(self):
        domain_model = PriceAlert(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            asset_type = AssetType.fiat,
            asset_id = "USD",
            currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.owner_id, self.owner_id)
        self.assertEqual(result.asset_type, AssetType.fiat.value)
        self.assertEqual(result.asset_id, "USD")
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.threshold_percent, 5)
        self.assertEqual(result.last_price, 0.85)
        self.assertEqual(result.last_price_time, self.last_price_time)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = PriceAlert(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            asset_type = AssetType.fiat,
            asset_id = "USD",
            currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = domain(db(original))

        self.assertEqual(result, original)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = PriceAlertDB(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            asset_type = AssetType.fiat.value,
            asset_id = "USD",
            currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )
        domain_model = PriceAlert(
            chat_id = UUID("33333333-3333-3333-3333-333333333333"),
            owner_id = UUID("44444444-4444-4444-4444-444444444444"),
            asset_type = AssetType.crypto,
            asset_id = "GBP",
            currency = "CHF",
            threshold_percent = 10,
            last_price = 1.15,
            last_price_time = datetime(2026, 1, 2, 12, 0, 0),
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.chat_id, self.chat_id)
        self.assertEqual(db_model.asset_type, AssetType.fiat.value)
        self.assertEqual(db_model.asset_id, "USD")
        self.assertEqual(db_model.currency, "EUR")
        self.assertEqual(db_model.owner_id, domain_model.owner_id)
        self.assertEqual(db_model.threshold_percent, domain_model.threshold_percent)
        self.assertEqual(db_model.last_price, domain_model.last_price)
        self.assertEqual(db_model.last_price_time, domain_model.last_price_time)
