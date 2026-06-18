import unittest
from datetime import datetime
from unittest.mock import Mock
from uuid import UUID

from db.crud.price_alert import PriceAlertCRUD
from db.crud.sponsorship import SponsorshipCRUD
from db.crud.tools_cache import ToolsCacheCRUD
from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.currency_alert_service import DATETIME_PRINT_FORMAT, CurrencyAlertService
from features.chat.telegram.currency_alert_responder import respond_with_currency_alerts
from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.external_tools.tool_choice_resolver import ToolChoiceResolver
from features.integrations.platform_bot_sdk import PlatformBotSDK
from util.translations_cache import TranslationsCache


class TelegramPriceAlertResponderTest(unittest.TestCase):

    mock_di: DI
    mock_scoped_di: DI
    mock_currency_alert_service: CurrencyAlertService
    mock_announcement_service: SysAnnouncementsService

    def setUp(self):
        # Create a DI mock and set required properties
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_crud = Mock(spec = UserCRUD)

        self.mock_di.chat_config_repo = Mock(spec = ChatConfigRepository)
        self.mock_di.chat_config_repo.get = self.__make_chat_config

        # noinspection PyPropertyAccess
        self.mock_di.price_alert_crud = Mock(spec = PriceAlertCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.tools_cache_crud = Mock(spec = ToolsCacheCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_crud = Mock(spec = SponsorshipCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_sdk = Mock(spec = TelegramBotSDK)
        self.mock_di.telegram_bot_sdk.api = Mock(spec = TelegramBotAPI)

        # Mock the currency_alert_service method to return a mock service
        self.mock_currency_alert_service = Mock(spec = CurrencyAlertService)
        self.mock_di.currency_alert_service.return_value = self.mock_currency_alert_service

        # Mock DI clone method and its dependencies
        # Create a single scoped_di that will be used by all tests
        self.mock_scoped_di = Mock()

        # Set up scoped DI dependencies

        # noinspection PyPropertyAccess
        self.mock_scoped_di.translations_cache = Mock(spec = TranslationsCache)
        # noinspection PyPropertyAccess
        self.mock_scoped_di.tool_choice_resolver = Mock(spec = ToolChoiceResolver)
        self.mock_scoped_di.sys_announcements_service = Mock(spec = SysAnnouncementsService)
        # noinspection PyPropertyAccess
        self.mock_platform_bot_sdk = Mock(spec = PlatformBotSDK)
        # noinspection PyPropertyAccess
        self.mock_scoped_di.platform_bot_sdk = Mock(return_value = self.mock_platform_bot_sdk)

        # Mock the announcements service instance
        self.mock_announcement_service = Mock(spec = SysAnnouncementsService)
        self.mock_scoped_di.sys_announcements_service.return_value = self.mock_announcement_service

        # Configure clone to return the same scoped_di
        self.mock_di.clone.return_value = self.mock_scoped_di

    @staticmethod
    def __make_chat_config(chat_id: UUID) -> ChatConfig:
        return ChatConfig(
            chat_id = chat_id,
            external_id = str(chat_id.int),
            title = "Test Chat",
            is_private = False,
            reply_chance_percent = 100,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            language_name = "English",
            language_iso_code = "en",
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

    # noinspection PyUnusedLocal
    def test_successful_announcements(self):
        # Create actual TriggeredAlert objects
        test_owner_id = UUID(int = 1)
        triggered_alerts = [
            CurrencyAlertService.TriggeredAlert(
                chat_id = UUID(int = 123), owner_id = test_owner_id,
                base_currency = "BTC", desired_currency = "USD", threshold_percent = 5,
                old_rate = 10000, old_rate_time = datetime(2023, 1, 1).strftime(DATETIME_PRINT_FORMAT),
                new_rate = 11000, new_rate_time = datetime(2023, 1, 2).strftime(DATETIME_PRINT_FORMAT),
                price_change_percent = 10,
            ),
            CurrencyAlertService.TriggeredAlert(
                chat_id = UUID(int = 456), owner_id = test_owner_id,
                base_currency = "ETH", desired_currency = "EUR", threshold_percent = 3,
                old_rate = 2000, old_rate_time = datetime(2023, 1, 1).strftime(DATETIME_PRINT_FORMAT),
                new_rate = 2100, new_rate_time = datetime(2023, 1, 2).strftime(DATETIME_PRINT_FORMAT),
                price_change_percent = 5,
            ),
        ]

        # Mock the service's instance methods
        self.mock_currency_alert_service.get_triggered_alerts.return_value = triggered_alerts

        # Mock translations cache
        self.mock_scoped_di.translations_cache.get.return_value = None  # No cached translation
        self.mock_scoped_di.translations_cache.save.return_value = "Test announcement"

        # Mock tool choice resolver
        mock_configured_tool = Mock()
        self.mock_scoped_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        # Mock the announcements service to return content
        mock_chat = Mock()
        mock_answer = Mock(content = "Test announcement")
        self.mock_announcement_service.execute.return_value = (mock_chat, mock_answer)

        result = respond_with_currency_alerts(self.mock_di)

        # Assertions
        self.assertEqual(result["alerts_triggered"], 2)
        self.assertEqual(result["chats_notified"], 2)
        self.assertEqual(result["announcements_created"], 2)
        self.assertEqual(result["chats_affected"], 2)

        # Verify the mock methods were called
        # noinspection PyUnresolvedReferences
        self.mock_currency_alert_service.get_triggered_alerts.assert_called_once()
        # Verify announcements were sent via scoped DI's platform_bot_sdk
        # noinspection PyUnresolvedReferences
        self.assertEqual(self.mock_platform_bot_sdk.send_text_message.call_count, 2)

    # noinspection PyUnusedLocal
    def test_no_triggered_alerts(self):
        # Mock the service's instance to return no alerts
        self.mock_currency_alert_service.get_triggered_alerts.return_value = []

        result = respond_with_currency_alerts(self.mock_di)

        # Assertions
        self.assertEqual(result["alerts_triggered"], 0)
        self.assertEqual(result["chats_notified"], 0)
        self.assertEqual(result["announcements_created"], 0)
        self.assertEqual(result["chats_affected"], 0)
        # noinspection PyUnresolvedReferences
        self.mock_platform_bot_sdk.send_text_message.assert_not_called()

    # noinspection PyUnusedLocal
    def test_announcement_creation_failure(self):
        test_owner_id = UUID(int = 1)
        triggered_alerts = [
            CurrencyAlertService.TriggeredAlert(
                chat_id = UUID(int = 123), owner_id = test_owner_id,
                base_currency = "BTC", desired_currency = "USD", threshold_percent = 5,
                old_rate = 10000, old_rate_time = datetime(2023, 1, 1).strftime(DATETIME_PRINT_FORMAT),
                new_rate = 11000, new_rate_time = datetime(2023, 1, 2).strftime(DATETIME_PRINT_FORMAT),
                price_change_percent = 10,
            ),
        ]

        # Mock the service's instance
        self.mock_currency_alert_service.get_triggered_alerts.return_value = triggered_alerts

        # Mock translations cache to return no cached content
        self.mock_scoped_di.translations_cache.get.return_value = None

        # Mock tool choice resolver
        mock_configured_tool = Mock()
        self.mock_scoped_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        # Mock the announcements service to return no content (failure)
        mock_chat = Mock()
        mock_answer = Mock(content = None)
        self.mock_announcement_service.execute.return_value = (mock_chat, mock_answer)

        result = respond_with_currency_alerts(self.mock_di)

        # Assertions - no announcements created due to failure
        self.assertEqual(result["alerts_triggered"], 1)
        self.assertEqual(result["chats_notified"], 0)
        self.assertEqual(result["announcements_created"], 0)
        self.assertEqual(result["chats_affected"], 1)
        # noinspection PyUnresolvedReferences
        self.mock_platform_bot_sdk.send_text_message.assert_not_called()

    # noinspection PyUnusedLocal
    def test_notification_failure(self):
        # Create actual TriggeredAlert objects
        test_owner_id = UUID(int = 1)
        triggered_alerts = [
            CurrencyAlertService.TriggeredAlert(
                chat_id = UUID(int = 123), owner_id = test_owner_id,
                base_currency = "BTC", desired_currency = "USD", threshold_percent = 5,
                old_rate = 10000, old_rate_time = datetime(2023, 1, 1).strftime(DATETIME_PRINT_FORMAT),
                new_rate = 11000, new_rate_time = datetime(2023, 1, 2).strftime(DATETIME_PRINT_FORMAT),
                price_change_percent = 10,
            ),
        ]

        # Mock the service's instance
        self.mock_currency_alert_service.get_triggered_alerts.return_value = triggered_alerts

        # Mock the translations cache to return cached content
        self.mock_scoped_di.translations_cache.get.return_value = "Cached announcement"

        self.mock_platform_bot_sdk.send_text_message.side_effect = Exception("Notification failed")

        result = respond_with_currency_alerts(self.mock_di)

        self.assertEqual(result["alerts_triggered"], 1)
        self.assertEqual(result["announcements_created"], 0)
        self.assertEqual(result["chats_affected"], 1)
        self.assertEqual(result["chats_notified"], 0)
        # noinspection PyUnresolvedReferences
        self.mock_platform_bot_sdk.send_text_message.assert_called_once()

    # noinspection PyUnusedLocal
    def test_cached_announcement(self):
        # Create actual TriggeredAlert objects
        test_owner_id = UUID(int = 1)
        triggered_alerts = [
            CurrencyAlertService.TriggeredAlert(
                chat_id = UUID(int = 123), owner_id = test_owner_id,
                base_currency = "BTC", desired_currency = "USD", threshold_percent = 5,
                old_rate = 10000, old_rate_time = datetime(2023, 1, 1).strftime(DATETIME_PRINT_FORMAT),
                new_rate = 11000, new_rate_time = datetime(2023, 1, 2).strftime(DATETIME_PRINT_FORMAT),
                price_change_percent = 10,
            ),
        ]

        # Mock the service's instance
        self.mock_currency_alert_service.get_triggered_alerts.return_value = triggered_alerts

        # Mock the translations cache to return cached content
        self.mock_scoped_di.translations_cache.get.return_value = "Cached announcement"

        result = respond_with_currency_alerts(self.mock_di)

        # Assertions
        self.assertEqual(result["alerts_triggered"], 1)
        self.assertEqual(result["chats_notified"], 1)
        self.assertEqual(result["announcements_created"], 0)
        self.assertEqual(result["chats_affected"], 1)
        # noinspection PyUnresolvedReferences
        self.mock_platform_bot_sdk.send_text_message.assert_called_once_with("123", "Cached announcement")
