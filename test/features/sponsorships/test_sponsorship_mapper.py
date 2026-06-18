import unittest
from datetime import datetime
from uuid import UUID

from db.model.sponsorship import SponsorshipDB
from features.sponsorships.sponsorship import Sponsorship
from features.sponsorships.sponsorship_mapper import db, domain


class SponsorshipMapperTest(unittest.TestCase):

    sponsor_id: UUID
    receiver_id: UUID
    sponsored_at: datetime
    accepted_at: datetime

    def setUp(self):
        self.sponsor_id = UUID("11111111-1111-1111-1111-111111111111")
        self.receiver_id = UUID("22222222-2222-2222-2222-222222222222")
        self.sponsored_at = datetime(2026, 1, 1, 12, 0, 0)
        self.accepted_at = datetime(2026, 1, 2, 12, 0, 0)

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = SponsorshipDB(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
            sponsored_at = self.sponsored_at,
            accepted_at = self.accepted_at,
        )

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, self.sponsor_id)
        self.assertEqual(result.receiver_id, self.receiver_id)
        self.assertEqual(result.sponsored_at, self.sponsored_at)
        self.assertEqual(result.accepted_at, self.accepted_at)

    def test_domain_maps_pending_sponsorship(self):
        db_model = SponsorshipDB(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
            sponsored_at = self.sponsored_at,
            accepted_at = None,
        )

        result = domain(db_model)

        self.assertEqual(result.sponsor_id, self.sponsor_id)
        self.assertEqual(result.receiver_id, self.receiver_id)
        self.assertEqual(result.sponsored_at, self.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_db_maps_all_fields(self):
        domain_model = Sponsorship(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
            sponsored_at = self.sponsored_at,
            accepted_at = self.accepted_at,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, self.sponsor_id)
        self.assertEqual(result.receiver_id, self.receiver_id)
        self.assertEqual(result.sponsored_at, self.sponsored_at)
        self.assertEqual(result.accepted_at, self.accepted_at)

    def test_domain_defaults_sponsored_at(self):
        domain_model = Sponsorship(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
        )

        self.assertIsNotNone(domain_model.sponsored_at)

    def test_db_maps_default_sponsored_at(self):
        domain_model = Sponsorship(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
            accepted_at = None,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, self.sponsor_id)
        self.assertEqual(result.receiver_id, self.receiver_id)
        self.assertEqual(result.sponsored_at, domain_model.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = Sponsorship(
            sponsor_id = self.sponsor_id,
            receiver_id = self.receiver_id,
            sponsored_at = self.sponsored_at,
            accepted_at = self.accepted_at,
        )

        result = domain(db(original))

        self.assertEqual(result, original)
