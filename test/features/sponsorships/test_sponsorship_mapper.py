import unittest
from datetime import timedelta
from uuid import uuid4

import stubs

from features.sponsorships.sponsorship_mapper import apply_to_db_model, db, domain


class SponsorshipMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.sponsorship_db()

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, db_model.sponsor_id)
        self.assertEqual(result.receiver_id, db_model.receiver_id)
        self.assertEqual(result.sponsored_at, db_model.sponsored_at)
        self.assertEqual(result.accepted_at, db_model.accepted_at)

    def test_domain_maps_pending_sponsorship(self):
        db_model = stubs.db.sponsorship_db(accepted_at = None)

        result = domain(db_model)

        self.assertEqual(result.sponsor_id, db_model.sponsor_id)
        self.assertEqual(result.receiver_id, db_model.receiver_id)
        self.assertEqual(result.sponsored_at, db_model.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.sponsorship()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, domain_model.sponsor_id)
        self.assertEqual(result.receiver_id, domain_model.receiver_id)
        self.assertEqual(result.sponsored_at, domain_model.sponsored_at)
        self.assertEqual(result.accepted_at, domain_model.accepted_at)

    def test_db_maps_pending_sponsorship(self):
        domain_model = stubs.domain.sponsorship(accepted_at = None)

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, domain_model.sponsor_id)
        self.assertEqual(result.receiver_id, domain_model.receiver_id)
        self.assertEqual(result.sponsored_at, domain_model.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = stubs.domain.sponsorship()

        result = domain(db(original))

        self.assertEqual(result, original)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.sponsorship_db()
        original_sponsor_id = db_model.sponsor_id
        original_receiver_id = db_model.receiver_id
        domain_model = stubs.domain.sponsorship(
            sponsor_id = uuid4(),
            receiver_id = uuid4(),
            sponsored_at = db_model.sponsored_at + timedelta(days = 1),
            accepted_at = None,
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.sponsor_id, original_sponsor_id)
        self.assertEqual(db_model.receiver_id, original_receiver_id)
        self.assertEqual(db_model.sponsored_at, domain_model.sponsored_at)
        self.assertIsNone(db_model.accepted_at)
