import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

from pydantic import SecretStr

from db.crud.price_alert import PriceAlertCRUD
from db.crud.sponsorship import SponsorshipCRUD
from db.crud.tools_cache import ToolsCacheCRUD
from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.price_alert import PriceAlert
from db.schema.user import User
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.currency_alert_service import CurrencyAlertService
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.currencies.exchange_rate_fetcher import ExchangeRateFetcher


class CurrencyAlertServiceTest(unittest.TestCase):

    mock_user_dao: UserCRUD
    mock_price_alert_dao: PriceAlertCRUD
    mock_tools_cache_dao: ToolsCacheCRUD
    mock_sponsorship_dao: SponsorshipCRUD
    mock_telegram_bot_sdk: TelegramBotSDK
    mock_exchange_rate_fetcher: ExchangeRateFetcher

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
        self.mock_di.price_alert_crud = self.mock_price_alert_dao = MagicMock(spec = PriceAlertCRUD)
        self.mock_di.user_crud = self.mock_user_dao = MagicMock(spec = UserCRUD)
        self.mock_di.tools_cache_crud = self.mock_tools_cache_dao = MagicMock(spec = ToolsCacheCRUD)
        self.mock_di.sponsorship_crud = self.mock_sponsorship_dao = MagicMock(spec = SponsorshipCRUD)
        self.mock_di.telegram_bot_sdk = self.mock_telegram_bot_sdk = MagicMock(spec = TelegramBotSDK)
        self.mock_di.exchange_rate_fetcher = self.mock_exchange_rate_fetcher = MagicMock(spec = ExchangeRateFetcher)
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

    def test_create_alert(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        self.mock_di.price_alert_crud.save.return_value = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 1.5,
            last_price_time = datetime.now(),
        )
        self.mock_di.exchange_rate_fetcher.execute.return_value = {"rate": 1.5}
        alert = service.create_alert("BTC", "USD", 5)
        self.assertEqual(alert.chat_id.hex, self.chat_id)
        self.assertEqual(alert.base_currency, "BTC")
        self.assertEqual(alert.desired_currency, "USD")
        self.assertEqual(alert.threshold_percent, 5)
        self.assertEqual(alert.last_price, 1.5)
        self.mock_di.price_alert_crud.save.assert_called_once()

    def test_get_all_alerts(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        mock_alerts = [
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                base_currency = "BTC",
                desired_currency = "USD",
                threshold_percent = 5,
                last_price = 1000,
                last_price_time = datetime.now(),
            ),
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                base_currency = "ETH",
                desired_currency = "EUR",
                threshold_percent = 3,
                last_price = 2000,
                last_price_time = datetime.now(),
            ),
        ]
        self.mock_di.price_alert_crud.get_alerts_by_chat.return_value = mock_alerts
        alerts = service.get_active_alerts()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].base_currency, "BTC")
        self.assertEqual(alerts[1].base_currency, "ETH")

    def test_delete_alert(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        mock_deleted_alert = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )
        self.mock_di.price_alert_crud.delete.return_value = mock_deleted_alert
        deleted_alert = service.delete_alert("BTC", "USD")
        assert deleted_alert is not None
        self.assertEqual(deleted_alert.base_currency, "BTC")
        self.assertEqual(deleted_alert.desired_currency, "USD")
        self.mock_di.price_alert_crud.delete.assert_called_once()

    def test_check_alerts(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        mock_alerts = [
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                base_currency = "BTC",
                desired_currency = "USD",
                threshold_percent = 5,
                last_price = 1000,
                last_price_time = datetime.now(),
            ),
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                base_currency = "ETH",
                desired_currency = "EUR",
                threshold_percent = 3,
                last_price = 2000,
                last_price_time = datetime.now(),
            ),
        ]
        self.mock_di.price_alert_crud.get_alerts_by_chat.return_value = mock_alerts
        self.mock_di.tools_cache_crud.get.return_value = None
        with patch.object(CurrencyAlertService, "get_triggered_alerts") as mock_get:
            mock_get.return_value = [
                CurrencyAlertService.TriggeredAlert(
                    chat_id = UUID(hex = self.chat_id),
                    owner_id = UUID(hex = self.user_id),
                    base_currency = "BTC",
                    desired_currency = "USD",
                    threshold_percent = 5,
                    old_rate = 1000,
                    old_rate_time = "2023-01-01 00:00 UTC",
                    new_rate = 1100,
                    new_rate_time = "2023-01-02 00:00 UTC",
                    price_change_percent = 10,
                ),
            ]
            triggered_alerts = service.get_triggered_alerts()
        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].base_currency, "BTC")
        self.assertEqual(triggered_alerts[0].desired_currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 10)

    def test_check_alerts_with_zero_last_price(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        mock_alerts = [
            PriceAlert(
                chat_id = UUID(hex = self.chat_id),
                owner_id = UUID(hex = self.user_id),
                base_currency = "BTC",
                desired_currency = "USD",
                threshold_percent = 5,
                last_price = 0,
                last_price_time = datetime.now(),
            ),
        ]
        self.mock_di.price_alert_crud.get_alerts_by_chat.return_value = mock_alerts
        self.mock_di.tools_cache_crud.get.return_value = None

        with patch.object(CurrencyAlertService, "get_triggered_alerts") as mock_get:
            mock_get.return_value = [
                CurrencyAlertService.TriggeredAlert(
                    chat_id = UUID(hex = self.chat_id),
                    owner_id = UUID(hex = self.user_id),
                    base_currency = "BTC",
                    desired_currency = "USD",
                    threshold_percent = 5,
                    old_rate = 0,
                    old_rate_time = "2023-01-01 00:00 UTC",
                    new_rate = 1000,
                    new_rate_time = "2023-01-02 00:00 UTC",
                    price_change_percent = 100000,
                ),
            ]
            triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].base_currency, "BTC")
        self.assertEqual(triggered_alerts[0].desired_currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 100000)
