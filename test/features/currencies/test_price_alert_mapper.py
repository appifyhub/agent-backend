import unittest
from datetime import datetime
from uuid import UUID

from db.model.price_alert import PriceAlertDB
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_mapper import db, domain


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
            base_currency = "USD",
            desired_currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.owner_id, self.owner_id)
        self.assertEqual(result.base_currency, "USD")
        self.assertEqual(result.desired_currency, "EUR")
        self.assertEqual(result.threshold_percent, 5)
        self.assertEqual(result.last_price, 0.85)
        self.assertEqual(result.last_price_time, self.last_price_time)

    def test_db_maps_all_fields(self):
        domain_model = PriceAlert(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            base_currency = "USD",
            desired_currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertEqual(result.owner_id, self.owner_id)
        self.assertEqual(result.base_currency, "USD")
        self.assertEqual(result.desired_currency, "EUR")
        self.assertEqual(result.threshold_percent, 5)
        self.assertEqual(result.last_price, 0.85)
        self.assertEqual(result.last_price_time, self.last_price_time)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = PriceAlert(
            chat_id = self.chat_id,
            owner_id = self.owner_id,
            base_currency = "USD",
            desired_currency = "EUR",
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = self.last_price_time,
        )

        result = domain(db(original))

        self.assertEqual(result, original)
