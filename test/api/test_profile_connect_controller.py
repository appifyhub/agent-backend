import unittest
from unittest.mock import Mock
from uuid import UUID

import stubs

from api.model.connect_key_response import ConnectKeyResponse
from api.profile_connect_controller import ProfileConnectController
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.connect.profile_connect_service import ProfileConnectService
from util.errors import InternalError


class ProfileConnectControllerTest(unittest.TestCase):

    def setUp(self) -> None:
        self.mock_di = Mock(spec = DI)
        self.controller = ProfileConnectController(self.mock_di)
        self.mock_profile_connect_service = Mock()
        self.mock_profile_connect_service.Result = ProfileConnectService.Result
        self.mock_profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.success,
            "Profiles connected successfully",
        )
        self.mock_di.profile_connect_service = self.mock_profile_connect_service

    def test_regenerate_connect_key_success(self) -> None:
        user = stubs.domain.user(id = UUID("12345678-1234-5678-1234-567812345678"))
        self.mock_di.authorization_service.authorize_for_user.return_value = user
        self.mock_profile_connect_service.regenerate_connect_key.return_value = "NEW-KEY-5678"

        response = self.controller.regenerate_connect_key(user.id.hex)

        self.assertIsInstance(response, ConnectKeyResponse)
        self.assertEqual(response.connect_key, "NEW-KEY-5678")
        self.mock_profile_connect_service.regenerate_connect_key.assert_called_once_with(user)

    def test_connect_profiles_success(self) -> None:
        user = stubs.domain.user(id = UUID("12345678-1234-5678-1234-567812345678"))
        self.mock_di.authorization_service.authorize_for_user.return_value = user
        expected_response = stubs.api.settings_link_response(settings_link = "https://example.com/profile-connected")
        self.mock_di.settings_controller.create_settings_link.return_value = expected_response

        response = self.controller.connect_profiles(
            user.id.hex,
            "new-key-0001",
            ChatConfigDB.ChatType.telegram,
        )

        self.assertIs(response, expected_response)
        self.mock_profile_connect_service.connect_profiles.assert_called_once()

    def test_connect_profiles_failure_result(self) -> None:
        user = stubs.domain.user(id = UUID("12345678-1234-5678-1234-567812345678"))
        self.mock_di.authorization_service.authorize_for_user.return_value = user
        self.mock_profile_connect_service.connect_profiles.return_value = (
            ProfileConnectService.Result.failure,
            "Failure",
        )

        with self.assertRaises(InternalError):
            self.controller.connect_profiles(
                user.id.hex,
                "new-key-0001",
                ChatConfigDB.ChatType.telegram,
            )
