import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock
from uuid import UUID

from api.model.settings_link_response import SettingsLinkResponse
from api.settings_controller import SettingsController
from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User, UserSave
from di.di import DI
from features.chat.command_processor import (
    COMMAND_CONNECT,
    COMMAND_HELP,
    COMMAND_SETTINGS,
    COMMAND_START,
    CommandProcessor,
    is_known_command,
)
from features.chat.config.chat_config import ChatConfig
from features.connect.profile_connect_service import ProfileConnectService
from features.integrations.integrations import resolve_agent_user
from features.integrations.platform_bot_sdk import PlatformBotSDK
from features.sponsorships.sponsorship_service import SponsorshipService
from util.error_codes import UNEXPECTED_ERROR


class CommandProcessorTest(unittest.TestCase):

    user: User
    chat: ChatConfig
    agent_user: UserSave
    mock_di: DI
    processor: CommandProcessor

    def setUp(self):
        self.user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.chat = ChatConfig(
            chat_id = UUID(int = 2),
            external_id = "test_chat_id",
            is_private = True,
            reply_chance_percent = 100,
            chat_type = ChatConfigDB.ChatType.telegram,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
        )
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)

        # Create mock DI with all required dependencies
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = self.user
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = self.chat
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        # noinspection PyPropertyAccess
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)

        # noinspection PyPropertyAccess
        self.mock_di.user_crud = Mock(spec = UserCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_service = Mock(spec = SponsorshipService)
        # noinspection PyPropertyAccess
        self.mock_di.profile_connect_service = Mock(spec = ProfileConnectService)
        # noinspection PyPropertyAccess
        self.mock_di.settings_controller = Mock(spec = SettingsController)
        # noinspection PyPropertyAccess
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk = Mock(return_value = mock_platform_sdk)
        self.mock_platform_sdk = mock_platform_sdk

        # Setup default return values
        self.mock_di.sponsorship_service.accept_sponsorship.return_value = False
        self.mock_di.settings_controller.create_settings_link.return_value = SettingsLinkResponse(
            settings_link = "https://example.com/settings?token=abc123",
        )
        self.mock_di.settings_controller.create_help_link.return_value = "https://example.com/features?token=abc123"

        self.processor = CommandProcessor(self.mock_di)

    def test_empty_input(self):
        result = self.processor.execute("")
        self.assertEqual(result.status, "ignored")

    def test_non_command_input(self):
        result = self.processor.execute("This is not a command")
        self.assertEqual(result.status, "ignored")

    def test_is_known_command_rejects_empty_or_blank(self):
        self.assertFalse(is_known_command("", "the_agent"))
        self.assertFalse(is_known_command(None, "the_agent"))
        self.assertFalse(is_known_command("   ", "the_agent"))

    def test_is_known_command_rejects_non_slash_input(self):
        self.assertFalse(is_known_command("hello", "the_agent"))
        self.assertFalse(is_known_command(f"hi /{COMMAND_HELP}", "the_agent"))  # slash not first token

    def test_is_known_command_rejects_unknown_command(self):
        self.assertFalse(is_known_command("/notacommand", "the_agent"))
        self.assertFalse(is_known_command("/notacommand@the_agent", "the_agent"))

    def test_is_known_command_rejects_malformed_slash_tokens(self):
        self.assertFalse(is_known_command("/", "the_agent"))
        self.assertFalse(is_known_command("/@the_agent", "the_agent"))
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@", "the_agent"))  # empty tag part

    def test_is_known_command_accepts_all_supported_commands(self):
        for command in (COMMAND_START, COMMAND_SETTINGS, COMMAND_HELP, COMMAND_CONNECT):
            self.assertTrue(is_known_command(f"/{command}", "the_agent"))
            self.assertTrue(is_known_command(f"/{command}@the_agent", "the_agent"))

    def test_is_known_command_accepts_command_with_trailing_args(self):
        self.assertTrue(is_known_command(f"/{COMMAND_CONNECT} ABC-123", "the_agent"))
        self.assertTrue(is_known_command(f"/{COMMAND_CONNECT}@the_agent ABC-123", "the_agent"))

    def test_is_known_command_rejects_known_command_with_wrong_tag(self):
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@otherbot", "the_agent"))

    def test_is_known_command_handles_missing_agent_handle(self):
        # untagged commands work even when the chat type has no resolvable agent handle
        self.assertTrue(is_known_command(f"/{COMMAND_HELP}", None))
        # tagged commands require a real handle to match against; None can never match
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@the_agent", None))

    def test_start_command_no_sponsorship(self):
        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_service.accept_sponsorship.assert_called_once_with(self.user)
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once_with(
            self.user.telegram_chat_id,
            "https://example.com/settings?token=abc123",
        )

    def test_start_command_with_sponsorship(self):
        self.mock_di.sponsorship_service.accept_sponsorship.return_value = True

        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_service.accept_sponsorship.assert_called_once_with(self.user)
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_not_called()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_not_called()

    def test_settings_command(self):
        result = self.processor.execute(f"/{COMMAND_SETTINGS}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_service.accept_sponsorship.assert_not_called()
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once_with(
            self.user.telegram_chat_id,
            "https://example.com/settings?token=abc123",
        )

    def test_start_command_with_bot_tag(self):
        bot_tag = self.agent_user.telegram_username
        result = self.processor.execute(f"/{COMMAND_START}@{bot_tag}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_settings_command_with_bot_tag(self):
        bot_tag = self.agent_user.telegram_username
        result = self.processor.execute(f"/{COMMAND_SETTINGS}@{bot_tag}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_wrong_bot_tagged(self):
        result = self.processor.execute(f"/{COMMAND_START}@wrong_bot")
        self.assertEqual(result.status, "ignored")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_not_called()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_not_called()

    def test_unknown_command(self):
        result = self.processor.execute("/unknown_command")
        self.assertEqual(result.status, "ignored")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_not_called()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_not_called()

    def test_start_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_START} some extra arguments")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_settings_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_SETTINGS} some extra arguments")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_exception_in_settings_controller(self):
        self.mock_di.settings_controller.create_settings_link.side_effect = Exception("Settings error")

        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)

    def test_exception_in_telegram_sdk(self):
        self.mock_platform_sdk.send_button_link.side_effect = Exception("Telegram error")

        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)

    def test_exception_in_sponsorship_service(self):
        self.mock_di.sponsorship_service.accept_sponsorship.side_effect = Exception("Sponsorship error")

        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)

    def test_help_command(self):
        result = self.processor.execute(f"/{COMMAND_HELP}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_help_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once_with(
            self.user.telegram_chat_id,
            "https://example.com/features?token=abc123",
        )

    def test_help_command_with_bot_tag(self):
        bot_tag = self.agent_user.telegram_username
        result = self.processor.execute(f"/{COMMAND_HELP}@{bot_tag}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_help_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_help_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_HELP} some extra arguments")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_help_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()

    def test_exception_in_help_link_creation(self):
        self.mock_di.settings_controller.create_help_link.side_effect = Exception("Help link error")

        result = self.processor.execute(f"/{COMMAND_HELP}")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)

    def test_connect_command_no_key_provided(self):
        result = self.processor.execute(f"/{COMMAND_CONNECT}")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once_with(
            self.user.telegram_chat_id,
            "https://example.com/settings?token=abc123",
        )

    def test_connect_command_successful(self):
        # Mock the Result enum on the service
        self.mock_di.profile_connect_service.Result = ProfileConnectService.Result
        self.mock_di.profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.success,
            "Profiles connected successfully!",
        )

        result = self.processor.execute(f"/{COMMAND_CONNECT} ABCD-EFGH-JKLM")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.profile_connect_service.connect_profiles.assert_called_once_with(
            self.user,
            "ABCD-EFGH-JKLM",
        )
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_text_message.assert_called_once_with(
            self.user.telegram_chat_id,
            "✅",
        )

    def test_connect_command_invalid_key(self):
        self.mock_di.profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.failure,
            "Invalid connect key",
        )

        result = self.processor.execute(f"/{COMMAND_CONNECT} INVALID-KEY")
        self.assertEqual(result.status, "success")
        # noinspection PyUnresolvedReferences
        self.mock_di.profile_connect_service.connect_profiles.assert_called_once()
        # Should send settings link instead
        # noinspection PyUnresolvedReferences
        self.mock_di.settings_controller.create_settings_link.assert_called_once()
        # noinspection PyUnresolvedReferences
        self.mock_platform_sdk.send_button_link.assert_called_once()
