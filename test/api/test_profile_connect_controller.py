import unittest
from datetime import date
from unittest.mock import Mock
from uuid import UUID

from api.model.connect_key_response import ConnectKeyResponse
from api.model.settings_link_response import SettingsLinkResponse
from api.profile_connect_controller import ProfileConnectController
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.connect.profile_connect_service import ProfileConnectService
from features.users.user import User
from util.errors import InternalError


class ProfileConnectControllerTest(unittest.TestCase):

    def setUp(self) -> None:
        self.mock_di = Mock(spec = DI)
        self.controller = ProfileConnectController(self.mock_di)
        self.user = User(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Test User",
            connect_key = "OLD-KEY-1234",
            telegram_user_id = 123,
            telegram_chat_id = "chat-1",
            created_at = date.today(),
        )
        self.mock_di.authorization_service.authorize_for_user.return_value = self.user
        self.mock_profile_connect_service = Mock()
        self.mock_profile_connect_service.Result = ProfileConnectService.Result
        self.mock_profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.success,
            "Profiles connected successfully",
        )
        self.mock_di.profile_connect_service = self.mock_profile_connect_service
        self.mock_di.settings_controller.create_settings_link.return_value = SettingsLinkResponse(
            settings_link = "https://example.com/settings",
        )

    def test_regenerate_connect_key_success(self) -> None:
        self.mock_profile_connect_service.regenerate_connect_key.return_value = "NEW-KEY-5678"

        response = self.controller.regenerate_connect_key(self.user.id.hex)

        self.assertIsInstance(response, ConnectKeyResponse)
        self.assertEqual(response.connect_key, "NEW-KEY-5678")
        self.mock_profile_connect_service.regenerate_connect_key.assert_called_once_with(self.user)

    def test_connect_profiles_success(self) -> None:
        response = self.controller.connect_profiles(
            self.user.id.hex,
            "new-key-0001",
            ChatConfigDB.ChatType.telegram,
        )

        self.assertIsInstance(response, SettingsLinkResponse)
        self.assertEqual(response.settings_link, "https://example.com/settings")
        self.mock_profile_connect_service.connect_profiles.assert_called_once()

    def test_connect_profiles_failure_result(self) -> None:
        self.mock_profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.failure,
            "Failure",
        )

        with self.assertRaises(InternalError):
            self.controller.connect_profiles(
                self.user.id.hex,
                "new-key-0001",
                ChatConfigDB.ChatType.telegram,
            )
