import unittest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

from langchain_core.messages import AIMessage
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from features.chat.config.chat_config import ChatConfig
from features.chat.dev_announcements_service import DevAnnouncementsService
from features.external_tools.tool_choice_resolver import ConfiguredTool
from util.errors import AuthorizationError, NotFoundError


class DevAnnouncementsServiceTest(unittest.TestCase):

    raw_announcement: str
    invoker_user_id: UUID
    user: User
    mock_di: MagicMock
    mock_configured_tool: ConfiguredTool

    def setUp(self):
        self.raw_announcement = "Test announcement"
        self.invoker_user_id = UUID("123e4567-e89b-12d3-a456-426614174000")
        self.user = User(
            id = self.invoker_user_id,
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 100,  # Changed from 1 to avoid conflict with chat external_ids
            open_ai_key = SecretStr("test_api_key"),
            replicate_key = SecretStr("test_replicate_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )

        # Mock DI
        self.mock_di = MagicMock()
        self.mock_di.invoker = self.user
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        self.mock_platform_sdk = MagicMock()
        self.mock_di.platform_bot_sdk = MagicMock(return_value = self.mock_platform_sdk)
        self.mock_di.chat_langchain_model.return_value = MagicMock()
        self.mock_di.user_crud.get_by_telegram_username.return_value = None
        self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = None
        self.mock_di.chat_config_repo.get_all.return_value = []
        self.mock_platform_sdk.send_text_message.return_value = {"result": {"message_id": 123}}
        self.mock_di.translations_cache.get.return_value = "Translated announcement"
        self.mock_di.translations_cache.save.return_value = "Translated announcement"
        self.mock_di.clone.return_value = self.mock_di

        # Mock configured tool
        # noinspection PyTypeChecker
        self.mock_configured_tool = MagicMock(spec = ConfiguredTool)

    @staticmethod
    def __create_mock_chat_config(external_id: str, language: str = "en"):
        return ChatConfig(
            chat_id = UUID(int = 1),
            external_id = external_id,
            language_iso_code = language,
            language_name = "English" if language == "en" else "Spanish",
            title = f"Chat {external_id}",
            is_private = True,
            reply_chance_percent = 100,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

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
        self.user.group = UserDB.Group.standard
        self.mock_di.invoker = self.user
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
            self.__create_mock_chat_config("1", "en"),
            self.__create_mock_chat_config("2", "es"),
        ]

        # Mock external ID resolution
        from unittest.mock import patch
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
            self.__create_mock_chat_config("1", "en"),
        ]
        self.mock_di.translations_cache.get.return_value = None  # Force translation attempt
        self.mock_di.translations_cache.save.side_effect = Exception("Translation failed")

        # Mock external ID resolution
        from unittest.mock import patch
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
            self.__create_mock_chat_config("1", "en"),
        ]
        self.mock_platform_sdk.send_text_message.side_effect = Exception("Notification failed")

        # Mock external ID resolution
        from unittest.mock import patch
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
        from unittest.mock import patch
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
        mock_llm.invoke.return_value = AIMessage(content = "Refined announcement")
        self.mock_di.chat_langchain_model.return_value = mock_llm

        target_user = User(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = "12345",
            telegram_user_id = 2,
            open_ai_key = SecretStr("test_api_key"),
            replicate_key = SecretStr("test_replicate_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        # Mock the platform-agnostic lookup
        from unittest.mock import patch
        with patch("features.chat.dev_announcements_service.lookup_user_by_handle") as mock_lookup:
            mock_lookup.return_value = target_user
            self.mock_di.chat_config_repo.get_by_external_identifiers.return_value = self.__create_mock_chat_config(
                external_id = "12345",
                language = "en",
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
            self.assertEqual(result["summaries_created"], 0)  # No new summaries because translations are cached

    def test_targeted_announcement_invalid_username(self):
        # Mock the platform-agnostic lookup to return None
        from unittest.mock import patch
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
        target_user = User(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = None,
            telegram_user_id = 2,
            open_ai_key = SecretStr("test_api_key"),
            replicate_key = SecretStr("test_replicate_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        # Mock the platform-agnostic lookup
        from unittest.mock import patch
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
        target_user = User(
            id = UUID("223e4567-e89b-12d3-a456-426614174000"),
            full_name = "Target User",
            telegram_username = "target_user",
            telegram_chat_id = "target_chat_id",
            telegram_user_id = 2,
            open_ai_key = SecretStr("test_api_key"),
            replicate_key = SecretStr("test_replicate_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        # Mock the platform-agnostic lookup
        from unittest.mock import patch
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
