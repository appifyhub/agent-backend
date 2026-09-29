from datetime import date
from typing import cast
from unittest import TestCase
from uuid import UUID

import stubs
from fakes.fake_url_shortener import FakeUrlShortener
from util.di_utils import di_for_tests

from api.model.connect_key_response import ConnectKeyResponse
from api.profile_connect_controller import ProfileConnectController
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.users.user import User
from util.error_codes import SPONSORSHIP_OPERATION_FAILED
from util.errors import InternalError


class ProfileConnectControllerTest(TestCase):

    di: DI
    controller: ProfileConnectController
    user: User

    def setUp(self) -> None:
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user(
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
            created_at = date(2023, 1, 1),
        ))
        self.di.inject_invoker(self.user)
        self.controller = self.di.profile_connect_controller

    def test_regenerate_connect_key_success(self) -> None:
        response = self.controller.regenerate_connect_key(self.user.id.hex)

        self.assertIsInstance(response, ConnectKeyResponse)
        self.assertNotEqual(response.connect_key, self.user.connect_key)
        self.assertRegex(response.connect_key, r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_connect_profiles_success(self) -> None:
        target = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            connect_key = "TARGET-KEY-1234",
            created_at = date(2024, 1, 1),
        ))
        expected_response = stubs.api.settings_link_response(settings_link = "https://example.com/profile-connected")
        shortener = cast(FakeUrlShortener, self.di.url_shortener("https://example.com/settings"))
        shortener.short_url = expected_response.settings_link

        response = self.controller.connect_profiles(
            self.user.id.hex,
            f"  {target.connect_key.lower()}  ",
            ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(response, expected_response)

    def test_connect_profiles_failure_result(self) -> None:
        with self.assertRaises(InternalError) as context:
            self.controller.connect_profiles(
                self.user.id.hex,
                "INVALID-KEY-HERE",
                ChatConfigDB.ChatType.telegram,
            )

        self.assertEqual(context.exception.error_code, SPONSORSHIP_OPERATION_FAILED)
        self.assertIn("Invalid connect key", str(context.exception))
