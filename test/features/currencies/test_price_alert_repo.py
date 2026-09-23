import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import stubs
from db.sql_util import SQLUtil

from features.currencies.asset_price import AssetType
from features.currencies.price_alert_repo import PriceAlertRepository


class PriceAlertRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: PriceAlertRepository
    owner_id: UUID

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.price_alert_repo()
        self.owner_id = self.sql.user_repo().save(stubs.domain.user()).id

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_price_alert(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        price_alert = stubs.domain.price_alert(
            chat_id = chat.chat_id,
            owner_id = self.owner_id,
            asset_type = AssetType.fiat,
            asset_id = "USD",
            currency = "EUR",
            last_price = 0.85,
            last_price_time = datetime(2026, 1, 1, 12, 0, 0),
        )

        result = self.repo.save(price_alert)

        self.assertEqual(result, price_alert)

    def test_get_returns_saved_price_alert(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        created = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )

        result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertEqual(result, created)

    def test_get_returns_none_when_missing(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())

        result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertIsNone(result)

    def test_composite_identity_keeps_assets_and_currencies_distinct(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        euro_alert = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )
        pound_alert = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "GBP",
            ),
        )
        stock_alert = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.stock,
                asset_id = "XNAS:USD",
                currency = "EUR",
            ),
        )

        euro_result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR")
        pound_result = self.repo.get(chat.chat_id, AssetType.fiat, "USD", "GBP")
        stock_result = self.repo.get(chat.chat_id, AssetType.stock, "XNAS:USD", "EUR")

        self.assertEqual(euro_result, euro_alert)
        self.assertEqual(pound_result, pound_alert)
        self.assertEqual(stock_result, stock_alert)

    def test_get_all_returns_price_alerts(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(external_id = "chat1"),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(chat_id = UUID("33333333-3333-4333-8333-c33333333333"), external_id = "chat2"),
        )
        first = self.repo.save(
            stubs.domain.price_alert(
                chat_id = first_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )
        second = self.repo.save(
            stubs.domain.price_alert(
                chat_id = second_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )

        results = self.repo.get_all()

        self.assertEqual({result.chat_id for result in results}, {first.chat_id, second.chat_id})

    def test_get_all_applies_pagination(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(external_id = "chat1"),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(chat_id = UUID("33333333-3333-4333-8333-c33333333333"), external_id = "chat2"),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = first_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = second_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )

        results = self.repo.get_all(skip = 0, limit = 1)

        self.assertEqual(len(results), 1)

    def test_get_all_by_chat_excludes_other_chats(self):
        first_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(external_id = "chat1"),
        )
        second_chat = self.sql.chat_config_repo().save(
            stubs.domain.chat_config(chat_id = UUID("33333333-3333-4333-8333-c33333333333"), external_id = "chat2"),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = first_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = first_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "GBP",
            ),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = second_chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )

        results = self.repo.get_all_by_chat(first_chat.chat_id)

        self.assertEqual({result.currency for result in results}, {"EUR", "GBP"})
        self.assertEqual({result.chat_id for result in results}, {first_chat.chat_id})

    def test_save_replaces_all_mutable_state(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        created = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
                last_price = 0.85,
                last_price_time = datetime(2026, 1, 1, 12, 0, 0),
            ),
        )
        replacement_owner = self.sql.user_repo().save(
            stubs.domain.user(
                id = UUID("33333333-3333-4333-8333-c33333333333"),
                telegram_user_id = None,
                whatsapp_user_id = None,
                connect_key = "REPL-OWNR-0001",
            ),
        )
        replacement = replace(
            created,
            owner_id = replacement_owner.id,
            threshold_percent = 10,
            last_price = 0.95,
            last_price_time = datetime(2026, 1, 2, 12, 0, 0),
        )

        result = self.repo.save(replacement)

        self.assertEqual(result, replacement)

    def test_delete_returns_deleted_price_alert(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        created = self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
            ),
        )

        result = self.repo.delete(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertEqual(result, created)
        self.assertIsNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR"))

    def test_delete_returns_none_when_missing(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())

        result = self.repo.delete(chat.chat_id, AssetType.fiat, "USD", "EUR")

        self.assertIsNone(result)

    def test_delete_stale_uses_strict_cutoff(self):
        chat = self.sql.chat_config_repo().save(stubs.domain.chat_config())
        cutoff = datetime(2026, 1, 2, 12, 0, 0)
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "EUR",
                last_price_time = cutoff - timedelta(seconds = 1),
            ),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "GBP",
                last_price_time = cutoff,
            ),
        )
        self.repo.save(
            stubs.domain.price_alert(
                chat_id = chat.chat_id,
                owner_id = self.owner_id,
                asset_type = AssetType.fiat,
                asset_id = "USD",
                currency = "CHF",
                last_price_time = cutoff + timedelta(seconds = 1),
            ),
        )

        deleted_count = self.repo.delete_stale(cutoff)

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "EUR"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "GBP"))
        self.assertIsNotNone(self.repo.get(chat.chat_id, AssetType.fiat, "USD", "CHF"))
