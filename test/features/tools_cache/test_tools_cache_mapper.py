import unittest
from datetime import datetime

from db.model.tools_cache import ToolsCacheDB
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_mapper import apply_to_db_model, db, domain


class ToolsCacheMapperTest(unittest.TestCase):

    created_at: datetime
    expires_at: datetime

    def setUp(self):
        self.created_at = datetime(2026, 1, 1, 12, 0, 0)
        self.expires_at = datetime(2026, 1, 2, 12, 0, 0)

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = ToolsCacheDB(
            key = "key",
            value = "value",
            created_at = self.created_at,
            expires_at = self.expires_at,
        )

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.key, "key")
        self.assertEqual(result.value, "value")
        self.assertEqual(result.created_at, self.created_at)
        self.assertEqual(result.expires_at, self.expires_at)

    def test_domain_maps_never_expiring_entry(self):
        db_model = ToolsCacheDB(
            key = "key",
            value = "value",
            created_at = self.created_at,
            expires_at = None,
        )

        result = domain(db_model)

        self.assertEqual(result.key, "key")
        self.assertEqual(result.value, "value")
        self.assertEqual(result.created_at, self.created_at)
        self.assertIsNone(result.expires_at)

    def test_db_maps_all_fields(self):
        domain_model = ToolsCache(
            key = "key",
            value = "value",
            created_at = self.created_at,
            expires_at = self.expires_at,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.key, "key")
        self.assertEqual(result.value, "value")
        self.assertEqual(result.created_at, self.created_at)
        self.assertEqual(result.expires_at, self.expires_at)

    def test_db_maps_default_created_at_and_null_expiration(self):
        domain_model = ToolsCache(key = "key", value = "value")

        result = db(domain_model)

        self.assertEqual(result.created_at, domain_model.created_at)
        self.assertIsNone(result.expires_at)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = ToolsCache(
            key = "key",
            value = "value",
            created_at = self.created_at,
            expires_at = self.expires_at,
        )

        result = domain(db(original))

        self.assertEqual(result, original)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = ToolsCacheDB(
            key = "stored-key",
            value = "old",
            created_at = self.created_at,
            expires_at = self.expires_at,
        )
        domain_model = ToolsCache(
            key = "different-key",
            value = "new",
            created_at = datetime(2026, 1, 3, 12, 0, 0),
            expires_at = None,
        )

        apply_to_db_model(domain_model, db_model)

        self.assertEqual(db_model.key, "stored-key")
        self.assertEqual(db_model.value, domain_model.value)
        self.assertEqual(db_model.created_at, domain_model.created_at)
        self.assertIsNone(db_model.expires_at)
