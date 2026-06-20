import unittest
from datetime import datetime, timedelta

from features.tools_cache.tools_cache import ToolsCache


class ToolsCacheTest(unittest.TestCase):

    def test_created_at_defaults_per_instance(self):
        before = datetime.now()

        first = ToolsCache(key = "key1", value = "value1")
        second = ToolsCache(key = "key2", value = "value2")

        after = datetime.now()
        self.assertGreaterEqual(first.created_at, before)
        self.assertLessEqual(first.created_at, after)
        self.assertGreaterEqual(second.created_at, first.created_at)
        self.assertLessEqual(second.created_at, after)
        self.assertIsNot(first.created_at, second.created_at)

    def test_is_expired_with_no_expiration(self):
        tools_cache = ToolsCache(key = "key1", value = "value1")

        self.assertFalse(tools_cache.is_expired())

    def test_is_expired_with_future_expiration(self):
        tools_cache = ToolsCache(
            key = "key2",
            value = "value2",
            expires_at = datetime.now() + timedelta(days = 1),
        )

        self.assertFalse(tools_cache.is_expired())

    def test_is_expired_with_past_expiration(self):
        tools_cache = ToolsCache(
            key = "key3",
            value = "value3",
            expires_at = datetime.now() - timedelta(days = 1),
        )

        self.assertTrue(tools_cache.is_expired())

    def test_create_key_preserves_existing_output(self):
        result = ToolsCache.create_key("prefix", "identifier")

        self.assertEqual(result, "3fffc53e8c62753274ae6ff244f2f4a4")

    def test_create_key_is_deterministic(self):
        first = ToolsCache.create_key("prefix", "identifier")
        second = ToolsCache.create_key("prefix", "identifier")

        self.assertEqual(first, second)
