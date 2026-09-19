import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

import stubs
from langchain_core.messages import AIMessage

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from features.chat.dev_announcements_service import DevAnnouncementsService
from features.external_tools.tool_choice_resolver import ConfiguredTool
from util.errors import AuthorizationError, NotFoundError


class DevAnnouncementsServiceTest(unittest.TestCase):

    raw_announcement: str
    invoker_user_id: UUID
    mock_di: MagicMock
    mock_configured_tool: ConfiguredTool

    def setUp(self):
        self.raw_announcement = "Test announcement"
        self.invoker_user_id = UUID("123e4567-e89b-12d3-a456-426614174000")
        user = stubs.domain.user(
            id = self.invoker_user_id,
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 100,
            group = UserDB.Group.developer,
        )

        # Mock DI
        self.mock_di = MagicMock()
        self.mock_di.invoker = user
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        self.mock_platform_sdk = MagicMock()
        self.mock_di.platform_bot_sdk = MagicMock(return_value = self.mock_platform_sdk)
        self.mock_di.chat_langchain_model.return_value = MagicMock()
        self.mock_di.user_repo.get_by_telegram_username.return_value = None
        self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = None
        self.mock_di.chat_config_repo.get_all.return_value = []
        self.mock_platform_sdk.send_text_message.return_value = {"result": {"message_id": 123}}
        self.mock_di.translations_cache.get.return_value = "Translated announcement"
        self.mock_di.translations_cache.save.return_value = "Translated announcement"
        self.mock_di.clone.return_value = self.mock_di

        # Mock configured tool
        # noinspection PyTypeChecker
        self.mock_configured_tool = MagicMock(spec = ConfiguredTool)

    def test_init_success(self):
        service = DevAnnouncementsService(
            self.raw_announcement,
            None,
            self.mock_configured_tool,
            self.mock_di,
        )
        self.assertIsInstance(service, DevAnnouncementsService)

    def test_init_user_not_found(self):
        self.mock_di.invoker.group = UserDB.Group.standard
        with self.assertRaises(AuthorizationError):
            DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )

    def test_init_user_not_developer(self):
        self.mock_di.invoker.group = UserDB.Group.standard
        with self.assertRaises(AuthorizationError):
            DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )

    def test_execute_success(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content = "Refined announcement")
        self.mock_di.chat_langchain_model.return_value = mock_llm

        self.mock_di.chat_config_repo.get_all.return_value = [
            stubs.domain.chat_config(
                external_id = "1",
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
            ),
            stubs.domain.chat_config(
                external_id = "2",
                language_iso_code = "es",
                language_name = "Spanish",
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
            ),
        ]

        # Mock external ID resolution
        with patch("features.integrations.integrations.resolve_external_id") as mock_resolve:
            def mock_resolve_side_effect(user, chat_type):
                if hasattr(user, "telegram_user_id") and user.telegram_user_id:
                    return str(user.telegram_user_id)
                # For agent user, return a different ID so chats don't get filtered out
                return "999999999"
            mock_resolve.side_effect = mock_resolve_side_effect

            service = DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )
            result = service.execute()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["chats_selected"], 2)
            self.assertEqual(result["chats_notified"], 2)
            self.assertEqual(result["summaries_created"], 0)  # No new summaries because translations are cached

    def test_execute_translation_failure(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content = "Refined announcement")
        self.mock_di.chat_langchain_model.return_value = mock_llm

        self.mock_di.chat_config_repo.get_all.return_value = [
            stubs.domain.chat_config(external_id = "1", release_notifications = ChatConfigDB.ReleaseNotifications.all),
        ]
        self.mock_di.translations_cache.get.return_value = None  # Force translation attempt
        self.mock_di.translations_cache.save.side_effect = Exception("Translation failed")

        # Mock external ID resolution
        with patch("features.integrations.integrations.resolve_external_id") as mock_resolve:
            def mock_resolve_side_effect(user, chat_type):
                if hasattr(user, "telegram_user_id") and user.telegram_user_id:
                    return str(user.telegram_user_id)
                # For agent user, return a different ID so chats don't get filtered out
                return "999999999"
            mock_resolve.side_effect = mock_resolve_side_effect

            service = DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )
            result = service.execute()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["chats_selected"], 1)
            self.assertEqual(result["chats_notified"], 0)
            self.assertEqual(result["summaries_created"], 0)

    def test_execute_notification_failure(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content = "Refined announcement")
        self.mock_di.chat_langchain_model.return_value = mock_llm

        self.mock_di.chat_config_repo.get_all.return_value = [
            stubs.domain.chat_config(external_id = "1", release_notifications = ChatConfigDB.ReleaseNotifications.all),
        ]
        self.mock_platform_sdk.send_text_message.side_effect = Exception("Notification failed")

        # Mock external ID resolution
        with patch("features.integrations.integrations.resolve_external_id") as mock_resolve:
            def mock_resolve_side_effect(user, chat_type):
                if hasattr(user, "telegram_user_id") and user.telegram_user_id:
                    return str(user.telegram_user_id)
                # For agent user, return a different ID so chats don't get filtered out
                return "999999999"
            mock_resolve.side_effect = mock_resolve_side_effect

            service = DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )
            result = service.execute()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["chats_selected"], 1)
            self.assertEqual(result["chats_notified"], 0)
            self.assertEqual(result["summaries_created"], 0)

    def test_execute_no_chats(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content = "Refined announcement")
        self.mock_di.chat_langchain_model.return_value = mock_llm

        self.mock_di.chat_config_repo.get_all.return_value = []

        # Mock external ID resolution
        with patch("features.integrations.integrations.resolve_external_id") as mock_resolve:
            def mock_resolve_side_effect(user, chat_type):
                if hasattr(user, "telegram_user_id") and user.telegram_user_id:
                    return str(user.telegram_user_id)
                # For agent user, return a different ID so chats don't get filtered out
                return "999999999"
            mock_resolve.side_effect = mock_resolve_side_effect

            service = DevAnnouncementsService(
                self.raw_announcement,
                None,
                self.mock_configured_tool,
                self.mock_di,
            )
            result = service.execute()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["chats_selected"], 0)
            self.assertEqual(result["chats_notified"], 0)
            self.assertEqual(result["summaries_created"], 0)

    def test_targeted_announcement_success(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content = [
            {"type": "thinking", "thinking": "Hidden reasoning"},
            {"type": "text", "text": "Refined announcement"},
        ])
        self.mock_di.chat_langchain_model.return_value = mock_llm
        self.mock_di.translations_cache.get.return_value = None
        self.mock_di.translations_cache.save.return_value = "Refined announcement"

        target_user = stubs.domain.user(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = "12345",
            telegram_user_id = 2,
        )

        # Mock the platform-agnostic lookup
        with patch("features.chat.dev_announcements_service.lookup_user_by_handle") as mock_lookup:
            mock_lookup.return_value = target_user
            self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = stubs.domain.chat_config(
                external_id = "12345",
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
            )

            service = DevAnnouncementsService(
                self.raw_announcement,
                "target_user",
                self.mock_configured_tool,
                self.mock_di,
            )
            result = service.execute()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["chats_selected"], 1)
            self.assertEqual(result["chats_notified"], 1)
            self.assertEqual(result["summaries_created"], 1)
            self.mock_di.translations_cache.save.assert_called_once_with(
                "Refined announcement",
                "English",
                "en",
            )

    def test_targeted_announcement_invalid_username(self):
        # Mock the platform-agnostic lookup to return None
        with patch("features.integrations.integrations.lookup_user_by_handle") as mock_lookup:
            mock_lookup.return_value = None

            with self.assertRaises(NotFoundError) as context:
                DevAnnouncementsService(
                    self.raw_announcement,
                    "nonexistent_user",
                    self.mock_configured_tool,
                    self.mock_di,
                )

            self.assertIn("Target user 'nonexistent_user' not found", str(context.exception))

    def test_targeted_announcement_no_chat_id(self):
        target_user = stubs.domain.user(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = None,
            telegram_user_id = 2,
        )

        # Mock the platform-agnostic lookup
        with patch("features.integrations.integrations.lookup_user_by_handle") as mock_lookup:
            mock_lookup.return_value = target_user

            with self.assertRaises(NotFoundError) as context:
                DevAnnouncementsService(
                    self.raw_announcement,
                    "target_user",
                    self.mock_configured_tool,
                    self.mock_di,
                )

            self.assertIn("not found", str(context.exception))

    def test_targeted_announcement_chat_not_found(self):
        target_user = stubs.domain.user(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = "target_chat_id",
            telegram_user_id = 2,
        )

        # Mock the platform-agnostic lookup
        with patch("features.integrations.integrations.lookup_user_by_handle") as mock_lookup:
            mock_lookup.return_value = target_user
            self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = None

            with self.assertRaises(NotFoundError) as context:
                DevAnnouncementsService(
                    self.raw_announcement,
                    "target_user",
                    self.mock_configured_tool,
                    self.mock_di,
                )

            self.assertIn("not found", str(context.exception))
