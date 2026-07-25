import unittest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

from db.sql_util import SQLUtil
from pydantic import SecretStr

from api.authorization_service import AuthorizationService
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership
from features.chat.membership.chat_membership_service import ChatMembershipService
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.currencies.asset_alert_service import DATETIME_PRINT_FORMAT, AssetAlertService
from features.currencies.asset_price import AssetPrice, AssetType
from features.currencies.asset_price_service import AssetPriceService
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_repo import PriceAlertRepository
from features.integrations.platform_bot_sdk import ChatAccess
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.users.user import User
from util.error_codes import NOT_CHAT_ADMIN, STOCK_QUOTE_FAILED
from util.errors import AuthorizationError, ExternalServiceError


class AssetAlertServiceTest(unittest.TestCase):

    mock_price_alert_repo: PriceAlertRepository
    mock_sponsorship_repo: SponsorshipRepository
    mock_telegram_bot_sdk: TelegramBotSDK
    mock_asset_price_service: AssetPriceService

    chat_id: str
    user_id: str
    user: User
    chat_config: ChatConfig

    def setUp(self):
        self.chat_id = UUID(int = 1).hex
        self.user_id = UUID(int = 1).hex
        # Create a DI mock and set required properties
        self.mock_di = MagicMock(spec = DI)
        self.mock_di.authorization_service = MagicMock()
        self.mock_di.price_alert_repo = self.mock_price_alert_repo = MagicMock(spec = PriceAlertRepository)
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo = MagicMock(spec = SponsorshipRepository)
        self.mock_di.telegram_bot_sdk = self.mock_telegram_bot_sdk = MagicMock(spec = TelegramBotSDK)
        self.mock_di.asset_price_service = self.mock_asset_price_service = MagicMock(spec = AssetPriceService)
        self.mock_asset_price_service.resolve_asset_type.side_effect = AssetPriceService.resolve_asset_type
        self.mock_asset_price_service.execute.return_value = self._asset_price()
        self.mock_di.invoker = self.user = User(
            id = UUID(hex = self.user_id),
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_api_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_di.authorization_service.validate_user.return_value = self.user
        self.chat_config = ChatConfig(
            chat_id = UUID(hex = self.chat_id),
            external_id = "test_chat_id",
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.mock_di.authorization_service.validate_chat.return_value = self.chat_config

    def _role_checked_service(
        self,
        access: ChatAccess,
        is_private: bool = False,
        existing_is_admin: bool | None = None,
    ) -> tuple[AssetAlertService, DI, SQLUtil, User, ChatConfig]:
        sql = SQLUtil()
        self.addCleanup(sql.end_session)
        user = sql.user_repo().save(
            User(
                full_name = "Role User",
                telegram_username = "role_user",
                telegram_chat_id = "private_chat",
                telegram_user_id = 123,
                open_ai_key = SecretStr("test_api_key"),
                group = UserDB.Group.standard,
                created_at = datetime.now().date(),
            ),
        )
        chat = sql.chat_config_repo().save(
            ChatConfig(
                external_id = "private_chat" if is_private else "group_chat",
                title = "Role Chat",
                is_private = is_private,
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
        )
        if existing_is_admin is not None:
            sql.chat_membership_repo().save(
                ChatMembership(
                    user_id = user.id,
                    chat_id = chat.chat_id,
                    is_admin = existing_is_admin,
                ),
            )

        di = MagicMock(spec = DI)
        di.user_repo = sql.user_repo()
        di.chat_config_repo = sql.chat_config_repo()
        di.chat_membership_repo = sql.chat_membership_repo()
        di.price_alert_repo = sql.price_alert_repo()
        di.asset_price_service = MagicMock(spec = AssetPriceService)
        di.asset_price_service.resolve_asset_type.side_effect = AssetPriceService.resolve_asset_type
        di.asset_price_service.execute.return_value = self._asset_price()
        di.invoker = user
        platform_sdk = MagicMock()
        platform_sdk.resolve_chat_access.return_value = access
        di.platform_bot_sdk.return_value = platform_sdk
        di.chat_membership_service = ChatMembershipService(di)
        di.authorization_service = AuthorizationService(di)
        return AssetAlertService(chat.chat_id.hex, di), di, sql, user, chat

    @staticmethod
    def _asset_price(
        asset: str = "BTC",
        asset_type: AssetType = AssetType.crypto,
        currency: str = "USD",
        unit_price: float = 1.5,
    ) -> AssetPrice:
        return AssetPrice(
            asset = asset,
            asset_type = asset_type,
            amount = 1,
            currency = currency,
            unit_price = unit_price,
            value = unit_price,
        )

    def test_create_alert(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.save.return_value = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 1.5,
            last_price_time = datetime.now(),
        )
        alert = service.create_alert("BTC", "USD", 5)
        self.assertEqual(alert.chat_id.hex, self.chat_id)
        self.assertEqual(alert.asset_id, "BTC")
        self.assertEqual(alert.currency, "USD")
        self.assertEqual(alert.threshold_percent, 5)
        self.assertEqual(alert.last_price, 1.5)
        saved = self.mock_price_alert_repo.save.call_args.args[0]
        self.assertEqual(saved.chat_id, UUID(hex = self.chat_id))
        self.assertEqual(saved.owner_id, UUID(hex = self.user_id))
        self.assertEqual(saved.asset_type, AssetType.crypto)
        self.assertEqual(saved.asset_id, "BTC")
        self.assertEqual(saved.currency, "USD")
        self.assertEqual(saved.threshold_percent, 5)
        self.assertEqual(saved.last_price, 1.5)
        self.mock_asset_price_service.execute.assert_called_once_with(
            asset = "BTC",
            currency = "USD",
            asset_type = None,
            force = False,
        )

    def test_create_stock_alert_persists_exchange_qualified_identity(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_asset_price_service.execute.return_value = self._asset_price(
            asset = "XNAS:AAPL",
            asset_type = AssetType.stock,
            unit_price = 210.5,
        )
        self.mock_price_alert_repo.save.side_effect = lambda alert: alert

        alert = service.create_alert("AAPL", "USD", 5, "stock")

        self.assertEqual(alert.asset_type, AssetType.stock)
        self.assertEqual(alert.asset_id, "XNAS:AAPL")
        self.assertEqual(alert.last_price, 210.5)
        saved = self.mock_price_alert_repo.save.call_args.args[0]
        self.assertEqual(saved.asset_type, AssetType.stock)
        self.assertEqual(saved.asset_id, "XNAS:AAPL")

    def test_admin_can_create_alert(self):
        service, di, sql, user, chat = self._role_checked_service(ChatAccess.admin)

        alert = service.create_alert("BTC", "USD", 5)

        stored = sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(alert.owner_id, user.id)
        self.assertEqual(stored.owner_id, user.id)
        self.assertEqual(stored.threshold_percent, 5)
        self.assertEqual(stored.last_price, 1.5)

    def test_admin_can_reconfigure_alert(self):
        service, di, sql, user, chat = self._role_checked_service(ChatAccess.admin)
        sql.price_alert_repo().save(
            PriceAlert(
                chat_id = chat.chat_id,
                owner_id = user.id,
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1.5,
                last_price_time = datetime(2023, 1, 1, 12, 0, 0),
            ),
        )
        di.asset_price_service.execute.return_value = self._asset_price(unit_price = 2.5)

        alert = service.create_alert("BTC", "USD", 8)

        stored = sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(alert.threshold_percent, 8)
        self.assertEqual(stored.owner_id, user.id)
        self.assertEqual(stored.threshold_percent, 8)
        self.assertEqual(stored.last_price, 2.5)

    def test_private_chat_owner_can_create_alert(self):
        service, di, sql, user, chat = self._role_checked_service(ChatAccess.owner, is_private = True)

        service.create_alert("BTC", "USD", 5)

        stored = sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.owner_id, user.id)
        self.assertEqual(stored.threshold_percent, 5)

    def test_get_all_alerts(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        mock_alerts = [
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1000,
                last_price_time = datetime.now(),
            ),
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                asset_type = AssetType.crypto,
                asset_id = "ETH",
                currency = "EUR",
                threshold_percent = 3,
                last_price = 2000,
                last_price_time = datetime.now(),
            ),
        ]
        self.mock_price_alert_repo.get_all_by_chat.return_value = mock_alerts
        alerts = service.get_active_alerts()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].asset_id, "BTC")
        self.assertEqual(alerts[1].asset_id, "ETH")
        self.mock_price_alert_repo.get_all_by_chat.assert_called_once_with(UUID(hex = self.chat_id))

    def test_get_all_alerts_without_target_chat(self):
        service = AssetAlertService(None, self.mock_di)
        self.mock_price_alert_repo.get_all.return_value = []

        alerts = service.get_active_alerts()

        self.assertEqual(alerts, [])
        self.mock_price_alert_repo.get_all.assert_called_once()

    def test_delete_alert(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        mock_deleted_alert = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )
        self.mock_price_alert_repo.delete.return_value = mock_deleted_alert
        deleted_alert = service.delete_alert("BTC", "USD")
        assert deleted_alert is not None
        self.assertEqual(deleted_alert.asset_id, "BTC")
        self.assertEqual(deleted_alert.currency, "USD")
        self.mock_price_alert_repo.delete.assert_called_once_with(
            UUID(hex = self.chat_id),
            AssetType.crypto,
            "BTC",
            "USD",
        )

    def test_admin_can_delete_alert(self):
        service, _, sql, user, chat = self._role_checked_service(ChatAccess.admin)
        sql.price_alert_repo().save(
            PriceAlert(
                chat_id = chat.chat_id,
                owner_id = user.id,
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1.5,
            ),
        )

        deleted_alert = service.delete_alert("BTC", "USD")

        self.assertIsNotNone(deleted_alert)
        self.assertIsNone(sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_delete_normalized_stock_identity_does_not_fetch_quote(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        stored = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.stock,
            asset_id = "XNAS:AAPL",
            currency = "USD",
            threshold_percent = 5,
            last_price = 210.5,
        )
        self.mock_price_alert_repo.delete.return_value = stored

        deleted = service.delete_alert(" xnas:aapl ", " usd ", "stock")

        self.assertIsNotNone(deleted)
        self.mock_price_alert_repo.delete.assert_called_once_with(
            UUID(hex = self.chat_id),
            AssetType.stock,
            "XNAS:AAPL",
            "USD",
        )
        self.mock_asset_price_service.execute.assert_not_called()

    def test_delete_unresolved_stock_forwards_provider_error(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.delete.return_value = None
        self.mock_asset_price_service.execute.side_effect = ExternalServiceError(
            "Specify an exchange",
            STOCK_QUOTE_FAILED,
        )

        with self.assertRaises(ExternalServiceError) as context:
            service.delete_alert("DHER", "EUR", "stock")

        self.assertEqual(context.exception.error_code, STOCK_QUOTE_FAILED)
        self.mock_asset_price_service.execute.assert_called_once_with(
            asset = "DHER",
            currency = "EUR",
            asset_type = "stock",
            force = False,
        )

    def test_member_cannot_create_alert(self):
        service, di, sql, _, chat = self._role_checked_service(ChatAccess.member)

        with self.assertRaises(AuthorizationError) as context:
            service.create_alert("BTC", "USD", 5)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        di.asset_price_service.execute.assert_not_called()
        self.assertIsNone(sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_member_cannot_reconfigure_alert(self):
        service, di, sql, user, chat = self._role_checked_service(ChatAccess.member)
        original_time = datetime(2023, 1, 1, 12, 0, 0)
        sql.price_alert_repo().save(
            PriceAlert(
                chat_id = chat.chat_id,
                owner_id = user.id,
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1.5,
                last_price_time = original_time,
            ),
        )

        with self.assertRaises(AuthorizationError) as context:
            service.create_alert("BTC", "USD", 8)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        di.asset_price_service.execute.assert_not_called()
        stored = sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.threshold_percent, 5)
        self.assertEqual(stored.last_price, 1.5)
        self.assertEqual(stored.last_price_time, original_time)

    def test_member_cannot_delete_alert(self):
        service, _, sql, user, chat = self._role_checked_service(ChatAccess.member)
        sql.price_alert_repo().save(
            PriceAlert(
                chat_id = chat.chat_id,
                owner_id = user.id,
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1.5,
            ),
        )

        with self.assertRaises(AuthorizationError) as context:
            service.delete_alert("BTC", "USD")

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        self.assertIsNotNone(sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_lost_admin_role_cannot_create_alert(self):
        service, di, sql, user, chat = self._role_checked_service(ChatAccess.member, existing_is_admin = True)

        with self.assertRaises(AuthorizationError) as context:
            service.create_alert("BTC", "USD", 5)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)
        di.asset_price_service.execute.assert_not_called()
        self.assertIsNone(sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD"))
        membership = sql.chat_membership_repo().get(user.id, chat.chat_id)
        self.assertIsNotNone(membership)
        self.assertFalse(membership.is_admin)

    def test_non_participant_cannot_create_alert(self):
        service, di, sql, _, chat = self._role_checked_service(None)

        with self.assertRaises(AuthorizationError):
            service.create_alert("BTC", "USD", 5)

        di.asset_price_service.execute.assert_not_called()
        self.assertIsNone(sql.price_alert_repo().get(chat.chat_id, AssetType.crypto, "BTC", "USD"))

    def test_listing_does_not_require_admin_role(self):
        service, _, sql, user, chat = self._role_checked_service(ChatAccess.member)
        sql.price_alert_repo().save(
            PriceAlert(
                chat_id = chat.chat_id,
                owner_id = user.id,
                asset_type = AssetType.crypto,
                asset_id = "BTC",
                currency = "USD",
                threshold_percent = 5,
                last_price = 1.5,
            ),
        )

        alerts = service.get_active_alerts()

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].asset_id, "BTC")

    def test_triggered_alert_refreshes_only_price_state(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        last_price_time = datetime(2023, 1, 1, 12, 0, 0)
        existing = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = last_price_time,
        )
        self.mock_price_alert_repo.get_all_by_chat.return_value = [existing]
        scoped_di = MagicMock()
        scoped_di.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 1100)
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(triggered_alerts[0].currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 10)
        self.assertEqual(triggered_alerts[0].old_price_time, last_price_time.strftime(DATETIME_PRINT_FORMAT))
        refreshed = self.mock_price_alert_repo.save.call_args.args[0]
        self.assertEqual(refreshed.chat_id, existing.chat_id)
        self.assertEqual(refreshed.owner_id, existing.owner_id)
        self.assertEqual(refreshed.asset_type, existing.asset_type)
        self.assertEqual(refreshed.asset_id, existing.asset_id)
        self.assertEqual(refreshed.currency, existing.currency)
        self.assertEqual(refreshed.threshold_percent, existing.threshold_percent)
        self.assertEqual(refreshed.last_price, 1100)
        self.assertGreater(refreshed.last_price_time, existing.last_price_time)
        self.mock_di.authorization_service.validate_chat_admin.assert_not_called()
        self.mock_di.clone.assert_called_once_with(
            invoker_id = existing.owner_id.hex,
            invoker_chat_id = existing.chat_id.hex,
        )
        scoped_di.asset_price_service.execute_normalized.assert_called_once_with(
            asset_id = "BTC",
            currency = "USD",
            asset_type = AssetType.crypto,
            force = False,
        )

    def test_triggered_alert_with_zero_last_price(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 0,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 1000)
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(triggered_alerts[0].currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 100000)

    def test_alert_below_threshold_is_not_triggered(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 1020)
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.mock_price_alert_repo.save.assert_not_called()

    def test_equivalent_owner_lookups_are_deduplicated_across_chats(self):
        service = AssetAlertService(None, self.mock_di)
        owner_id = UUID(int = 7)
        alerts = [
            PriceAlert(
                chat_id = UUID(int = chat_number),
                owner_id = owner_id,
                asset_type = AssetType.stock,
                asset_id = "XNAS:AAPL",
                currency = "USD",
                threshold_percent = 5,
                last_price = 100,
            )
            for chat_number in (10, 11)
        ]
        self.mock_price_alert_repo.get_all.return_value = alerts
        scoped_di = MagicMock()
        scoped_di.asset_price_service.execute_normalized.return_value = self._asset_price(
            asset = "XNAS:AAPL",
            asset_type = AssetType.stock,
            unit_price = 110,
        )
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 2)
        self.mock_di.clone.assert_called_once()
        scoped_di.asset_price_service.execute_normalized.assert_called_once()

    def test_same_lookup_for_different_owners_uses_each_owner_scope(self):
        service = AssetAlertService(None, self.mock_di)
        alerts = [
            PriceAlert(
                chat_id = UUID(int = owner_number + 10),
                owner_id = UUID(int = owner_number),
                asset_type = AssetType.stock,
                asset_id = "XNAS:AAPL",
                currency = "USD",
                threshold_percent = 5,
                last_price = 100,
            )
            for owner_number in (1, 2)
        ]
        self.mock_price_alert_repo.get_all.return_value = alerts
        first_scope = MagicMock()
        second_scope = MagicMock()
        first_scope.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 102)
        second_scope.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 102)
        self.mock_di.clone.side_effect = [first_scope, second_scope]

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.assertEqual(self.mock_di.clone.call_count, 2)
        self.assertEqual(first_scope.asset_price_service.execute_normalized.call_count, 1)
        self.assertEqual(second_scope.asset_price_service.execute_normalized.call_count, 1)

    def test_price_fetch_failure_skips_alert(self):
        service = AssetAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.asset_price_service.execute_normalized.side_effect = ExternalServiceError(
            "Price unavailable",
            STOCK_QUOTE_FAILED,
        )
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.mock_price_alert_repo.save.assert_not_called()

    def test_failed_lookup_is_deduplicated_and_distinct_alert_continues(self):
        service = AssetAlertService(None, self.mock_di)
        owner_id = UUID(int = 7)
        failed_alerts = [
            PriceAlert(
                chat_id = UUID(int = chat_number),
                owner_id = owner_id,
                asset_type = AssetType.stock,
                asset_id = "XNAS:AAPL",
                currency = "USD",
                threshold_percent = 5,
                last_price = 100,
            )
            for chat_number in (10, 11)
        ]
        successful_alert = PriceAlert(
            chat_id = UUID(int = 12),
            owner_id = owner_id,
            asset_type = AssetType.crypto,
            asset_id = "BTC",
            currency = "USD",
            threshold_percent = 5,
            last_price = 100,
        )
        self.mock_price_alert_repo.get_all.return_value = [*failed_alerts, successful_alert]
        failed_scope = MagicMock()
        failed_scope.asset_price_service.execute_normalized.side_effect = ExternalServiceError(
            "Price unavailable",
            STOCK_QUOTE_FAILED,
        )
        successful_scope = MagicMock()
        successful_scope.asset_price_service.execute_normalized.return_value = self._asset_price(unit_price = 110)
        self.mock_di.clone.side_effect = [failed_scope, successful_scope]

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].asset_id, "BTC")
        self.assertEqual(self.mock_di.clone.call_count, 2)
