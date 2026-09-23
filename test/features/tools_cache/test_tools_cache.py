import unittest
from datetime import datetime, timedelta

import stubs

from features.tools_cache.tools_cache import ToolsCache


class ToolsCacheTest(unittest.TestCase):

    def test_is_expired_with_no_expiration(self):
        tools_cache = stubs.domain.tools_cache(expires_at = None)

        self.assertFalse(tools_cache.is_expired())

    def test_is_expired_with_future_expiration(self):
        tools_cache = stubs.domain.tools_cache(
            expires_at = datetime.now() + timedelta(days = 1),
        )

        self.assertFalse(tools_cache.is_expired())

    def test_is_expired_with_past_expiration(self):
        tools_cache = stubs.domain.tools_cache(
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
