import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from db.sql_util import SQLUtil

from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository


class ToolsCacheRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: ToolsCacheRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.tools_cache_repo()

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_tools_cache(self):
        created_at = datetime(2026, 1, 1, 12, 0, 0)
        expires_at = datetime(2026, 1, 2, 12, 0, 0)
        tools_cache = ToolsCache(
            key = "key",
            value = "value",
            created_at = created_at,
            expires_at = expires_at,
        )

        result = self.repo.save(tools_cache)

        self.assertEqual(result, tools_cache)

    def test_get_returns_saved_tools_cache(self):
        created = self.repo.save(ToolsCache(key = "key", value = "value"))

        result = self.repo.get(created.key)

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        result = self.repo.get("missing")

        self.assertIsNone(result)

    def test_get_all_tools_caches(self):
        first = self.repo.save(ToolsCache(key = "key1", value = "value1"))
        second = self.repo.save(ToolsCache(key = "key2", value = "value2"))

        results = self.repo.get_all()

        self.assertEqual({result.key for result in results}, {first.key, second.key})

    def test_get_all_applies_pagination(self):
        self.repo.save(ToolsCache(key = "key1", value = "value1"))
        self.repo.save(ToolsCache(key = "key2", value = "value2"))

        results = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(results), 1)

    def test_save_replaces_all_mutable_fields(self):
        created = self.repo.save(ToolsCache(
            key = "key",
            value = "old-value",
            created_at = datetime(2026, 1, 1, 12, 0, 0),
            expires_at = datetime(2026, 1, 2, 12, 0, 0),
        ))
        replacement = replace(
            created,
            value = "new-value",
            created_at = datetime(2026, 2, 1, 12, 0, 0),
            expires_at = datetime(2026, 2, 2, 12, 0, 0),
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)

    def test_save_can_clear_expiration(self):
        created = self.repo.save(ToolsCache(
            key = "key",
            value = "value",
            expires_at = datetime(2026, 1, 2, 12, 0, 0),
        ))

        result = self.repo.save(replace(created, expires_at = None))

        self.assertIsNone(result.expires_at)
        self.assertFalse(result.is_expired())

    def test_delete_returns_deleted_tools_cache(self):
        created = self.repo.save(ToolsCache(key = "key", value = "value"))

        result = self.repo.delete(created.key)

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(created.key))

    def test_delete_returns_none_when_missing(self):
        result = self.repo.delete("missing")

        self.assertIsNone(result)

    def test_delete_expired(self):
        now = datetime.now()
        self.repo.save(ToolsCache(
            key = "expired",
            value = "value",
            expires_at = now - timedelta(days = 1),
        ))
        self.repo.save(ToolsCache(
            key = "future",
            value = "value",
            expires_at = now + timedelta(days = 1),
        ))
        self.repo.save(ToolsCache(
            key = "never",
            value = "value",
            expires_at = None,
        ))

        deleted_count = self.repo.delete_expired()

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get("expired"))
        self.assertIsNotNone(self.repo.get("future"))
        self.assertIsNotNone(self.repo.get("never"))
