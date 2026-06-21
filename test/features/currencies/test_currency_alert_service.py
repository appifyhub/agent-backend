import unittest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import SecretStr

from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.currencies.currency_alert_service import DATETIME_PRINT_FORMAT, CurrencyAlertService
from features.currencies.exchange_rate_fetcher import ExchangeRateFetcher
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_repo import PriceAlertRepository
from features.sponsorships.sponsorship_repo import SponsorshipRepository


class CurrencyAlertServiceTest(unittest.TestCase):

    mock_user_dao: UserCRUD
    mock_price_alert_repo: PriceAlertRepository
    mock_sponsorship_repo: SponsorshipRepository
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
        self.mock_di.price_alert_repo = self.mock_price_alert_repo = MagicMock(spec = PriceAlertRepository)
        self.mock_di.user_crud = self.mock_user_dao = MagicMock(spec = UserCRUD)
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo = MagicMock(spec = SponsorshipRepository)
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
        self.mock_price_alert_repo.save.return_value = PriceAlert(
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
        saved = self.mock_price_alert_repo.save.call_args.args[0]
        self.assertEqual(saved.chat_id, UUID(hex = self.chat_id))
        self.assertEqual(saved.owner_id, UUID(hex = self.user_id))
        self.assertEqual(saved.base_currency, "BTC")
        self.assertEqual(saved.desired_currency, "USD")
        self.assertEqual(saved.threshold_percent, 5)
        self.assertEqual(saved.last_price, 1.5)

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
        self.mock_price_alert_repo.get_all_by_chat.return_value = mock_alerts
        alerts = service.get_active_alerts()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].base_currency, "BTC")
        self.assertEqual(alerts[1].base_currency, "ETH")
        self.mock_price_alert_repo.get_all_by_chat.assert_called_once_with(UUID(hex = self.chat_id))

    def test_get_all_alerts_without_target_chat(self):
        service = CurrencyAlertService(None, self.mock_di)
        self.mock_price_alert_repo.get_all.return_value = []

        alerts = service.get_active_alerts()

        self.assertEqual(alerts, [])
        self.mock_price_alert_repo.get_all.assert_called_once()

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
        self.mock_price_alert_repo.delete.return_value = mock_deleted_alert
        deleted_alert = service.delete_alert("BTC", "USD")
        assert deleted_alert is not None
        self.assertEqual(deleted_alert.base_currency, "BTC")
        self.assertEqual(deleted_alert.desired_currency, "USD")
        self.mock_price_alert_repo.delete.assert_called_once_with(UUID(hex = self.chat_id), "BTC", "USD")

    def test_triggered_alert_refreshes_only_price_state(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        last_price_time = datetime(2023, 1, 1, 12, 0, 0)
        existing = PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = last_price_time,
        )
        self.mock_price_alert_repo.get_all_by_chat.return_value = [existing]
        scoped_di = MagicMock()
        scoped_di.exchange_rate_fetcher.execute.return_value = {"rate": 1100}
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].base_currency, "BTC")
        self.assertEqual(triggered_alerts[0].desired_currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 10)
        self.assertEqual(triggered_alerts[0].old_rate_time, last_price_time.strftime(DATETIME_PRINT_FORMAT))
        refreshed = self.mock_price_alert_repo.save.call_args.args[0]
        self.assertEqual(refreshed.chat_id, existing.chat_id)
        self.assertEqual(refreshed.owner_id, existing.owner_id)
        self.assertEqual(refreshed.base_currency, existing.base_currency)
        self.assertEqual(refreshed.desired_currency, existing.desired_currency)
        self.assertEqual(refreshed.threshold_percent, existing.threshold_percent)
        self.assertEqual(refreshed.last_price, 1100)
        self.assertGreater(refreshed.last_price_time, existing.last_price_time)

    def test_triggered_alert_with_zero_last_price(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 0,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.exchange_rate_fetcher.execute.return_value = {"rate": 1000}
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0].base_currency, "BTC")
        self.assertEqual(triggered_alerts[0].desired_currency, "USD")
        self.assertEqual(triggered_alerts[0].price_change_percent, 100000)

    def test_alert_below_threshold_is_not_triggered(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.exchange_rate_fetcher.execute.return_value = {"rate": 1020}
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.mock_price_alert_repo.save.assert_not_called()

    def test_rate_fetch_failure_skips_alert(self):
        service = CurrencyAlertService(self.chat_id, self.mock_di)
        self.mock_price_alert_repo.get_all_by_chat.return_value = [PriceAlert(
            chat_id = UUID(hex = self.chat_id),
            owner_id = UUID(hex = self.user_id),
            base_currency = "BTC",
            desired_currency = "USD",
            threshold_percent = 5,
            last_price = 1000,
            last_price_time = datetime.now(),
        )]
        scoped_di = MagicMock()
        scoped_di.exchange_rate_fetcher.execute.side_effect = RuntimeError("rate unavailable")
        self.mock_di.clone.return_value = scoped_di

        triggered_alerts = service.get_triggered_alerts()

        self.assertEqual(triggered_alerts, [])
        self.mock_price_alert_repo.save.assert_not_called()
