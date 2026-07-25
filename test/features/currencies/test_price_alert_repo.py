import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from db.sql_util import SQLUtil

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.currencies.asset_price import AssetType
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_repo import PriceAlertRepository
from features.users.user import User


class PriceAlertRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: PriceAlertRepository
    owner_id: UUID

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.price_alert_repo()
        self.owner_id = self.sql.user_repo().save(User()).id

    def tearDown(self):
        self.sql.end_session()

    def _create_chat(self, external_id: str) -> ChatConfig:
        return self.sql.chat_config_repo().save(ChatConfig(
            external_id = external_id,
            chat_type = ChatConfigDB.ChatType.telegram,
        ))

    def _price_alert(
        self,
        chat_id: UUID,
        asset_type: AssetType = AssetType.fiat,
        asset_id: str = "USD",
        currency: str = "EUR",
        last_price_time: datetime | None = None,
    ) -> PriceAlert:
        return PriceAlert(
            chat_id = chat_id,
            owner_id = self.owner_id,
            asset_type = asset_type,
            asset_id = asset_id,
            currency = currency,
            threshold_percent = 5,
            last_price = 0.85,
            last_price_time = last_price_time or datetime.now(),
        )

    def test_save_creates_price_alert(self):
        chat = self._create_chat("chat1")
        price_alert = self._price_alert(
            chat_id = chat.chat_id,
            last_price_time = datetime(2026, 1, 1, 12, 0, 0),
        )

        result = self.repo.save(price_alert)

        self.assertEqual(result, price_alert)

    def test_get_returns_saved_price_alert(self):
        chat = self._create_chat("chat1")
        created = self.repo.save(self._price_alert(chat.chat_id))

        result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        chat = self._create_chat("chat1")

        result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertIsNone(result)

    def test_composite_identity_keeps_assets_and_currencies_distinct(self):
        chat = self._create_chat("chat1")
        euro_alert = self.repo.save(self._price_alert(chat.chat_id, currency = "EUR"))
        pound_alert = self.repo.save(self._price_alert(chat.chat_id, currency = "GBP"))
        stock_alert = self.repo.save(self._price_alert(
            chat.chat_id,
            asset_type = AssetType.stock,
            asset_id = "XNAS:USD",
            currency = "EUR",
        ))

        euro_result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")
        pound_result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "GBP")
        stock_result = self.repo.get(chat.chat_id, AssetType.stock, "XNAS:USD", "EUR")

        self.assertEqual(euro_result, euro_alert)
        self.assertEqual(pound_result, pound_alert)
        self.assertEqual(stock_result, stock_alert)

    def test_get_all_returns_price_alerts(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        first = self.repo.save(self._price_alert(first_chat.chat_id))
        second = self.repo.save(self._price_alert(second_chat.chat_id))

        results = self.repo.get_all()

        self.assertEqual({result.chat_id for result in results}, {first.chat_id, second.chat_id})

    def test_get_all_applies_pagination(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        self.repo.save(self._price_alert(first_chat.chat_id))
        self.repo.save(self._price_alert(second_chat.chat_id))

        results = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(results), 1)

    def test_get_all_by_chat_excludes_other_chats(self):
        first_chat = self._create_chat("chat1")
        second_chat = self._create_chat("chat2")
        first = self.repo.save(self._price_alert(first_chat.chat_id, currency = "EUR"))
        second = self.repo.save(self._price_alert(first_chat.chat_id, currency = "GBP"))
        self.repo.save(self._price_alert(second_chat.chat_id))

        results = self.repo.get_all_by_chat(first_chat.chat_id)

        self.assertEqual({result.currency for result in results}, {"EUR", "GBP"})
        self.assertEqual({result.chat_id for result in results}, {first.chat_id, second.chat_id})

    def test_save_replaces_all_mutable_state(self):
        chat = self._create_chat("chat1")
        created = self.repo.save(self._price_alert(
            chat.chat_id,
            last_price_time = datetime(2026, 1, 1, 12, 0, 0),
        ))
        replacement_owner = self.sql.user_repo().save(User()).id
        replacement = replace(
            created,
            owner_id = replacement_owner,
            threshold_percent = 10,
            last_price = 0.95,
            last_price_time = datetime(2026, 1, 2, 12, 0, 0),
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)

    def test_delete_returns_deleted_price_alert(self):
        chat = self._create_chat("chat1")
        created = self.repo.save(self._price_alert(chat.chat_id))

        result = self.repo.delete(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR"))

    def test_delete_returns_none_when_missing(self):
        chat = self._create_chat("chat1")

        result = self.repo.delete(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertIsNone(result)

    def test_delete_stale_uses_strict_cutoff(self):
        chat = self._create_chat("chat1")
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(self._price_alert(
            chat.chat_id,
            currency = "EUR",
            last_price_time = cutoff - timedelta(seconds = 1),
        ))
        self.repo.save(self._price_alert(
            chat.chat_id,
            currency = "GBP",
            last_price_time = cutoff,
        ))
        self.repo.save(self._price_alert(
            chat.chat_id,
            currency = "CHF",
            last_price_time = cutoff + timedelta(seconds = 1),
        ))

        deleted_count = self.repo.delete_stale(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "GBP"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "CHF"))
