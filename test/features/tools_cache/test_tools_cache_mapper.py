import unittest
from dataclasses import replace
from datetime import timedelta

import stubs

from features.tools_cache.tools_cache_mapper import apply_to_db_model, db, domain


class ToolsCacheMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.tools_cache_db()
        db_model.expires_at = db_model.created_at + timedelta(days = 1)

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.key, db_model.key)
        self.assertEqual(result.value, db_model.value)
        self.assertEqual(result.created_at, db_model.created_at)
        self.assertEqual(result.expires_at, db_model.expires_at)

    def test_domain_maps_never_expiring_entry(self):
        db_model = stubs.db.tools_cache_db()

        result = domain(db_model)

        self.assertEqual(result.key, db_model.key)
        self.assertEqual(result.value, db_model.value)
        self.assertEqual(result.created_at, db_model.created_at)
        self.assertIsNone(result.expires_at)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.tools_cache()
        domain_model = replace(
            domain_model,
            expires_at = domain_model.created_at + timedelta(days = 1),
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.key, domain_model.key)
        self.assertEqual(result.value, domain_model.value)
        self.assertEqual(result.created_at, domain_model.created_at)
        self.assertEqual(result.expires_at, domain_model.expires_at)

    def test_db_maps_default_created_at_and_null_expiration(self):
        domain_model = stubs.domain.tools_cache()

        result = db(domain_model)

        self.assertEqual(result.created_at, domain_model.created_at)
        self.assertIsNone(result.expires_at)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = stubs.domain.tools_cache()
        original = replace(
            original,
            expires_at = original.created_at + timedelta(days = 1),
        )

        result = domain(db(original))

        self.assertEqual(result, original)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.tools_cache_db()
        db_model.expires_at = db_model.created_at + timedelta(days = 1)
        stored_key = db_model.key
        domain_model = stubs.domain.tools_cache(
            key = f"different-{db_model.key}",
            value = f"new-{db_model.value}",
            created_at = db_model.created_at + timedelta(days = 2),
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.key, stored_key)
        self.assertEqual(db_model.value, domain_model.value)
        self.assertEqual(db_model.created_at, domain_model.created_at)
        self.assertIsNone(db_model.expires_at)
