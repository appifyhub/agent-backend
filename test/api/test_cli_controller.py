from dataclasses import replace
from datetime import timedelta
from typing import cast
from unittest import TestCase
from uuid import uuid4

import stubs
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from pydantic import SecretStr
from util.di_utils import di_for_tests

from api.cli_controller import CliController
from api.model.cli_chat_response import CliChatResponse
from di.di import DI
from features.users.user import User
from util.error_codes import (
    CLI_ACCESS_REVOKED,
    INVALID_PLATFORM,
    NOT_TARGET_USER,
    USER_NOT_FOUND,
    WAITLIST_ACCOUNT_NOT_ACTIVE,
)
from util.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError


class CliControllerTest(TestCase):

    di: DI
    controller: CliController
    owner: User
    telegram: FakeTelegramBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.owner = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.owner)
        self.controller = self.di.cli_controller
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)

    def __claims(self, generation: int | None = None, user_id: str | None = None):
        return stubs.api.cli_token_claims(
            user_id = user_id or self.owner.id.hex,
            generation = self.owner.cli_token_generation if generation is None else generation,
        )

    def __stored_owner(self) -> User:
        return self.di.authorization_service.validate_user(self.owner.id)

    def __save_other_user(self) -> User:
        return self.di.user_repo.save(stubs.domain.user(
            id = None, connect_key = "OTHER-KEY-001", telegram_user_id = 987654321, telegram_chat_id = "987654321",
            telegram_username = "other_user", whatsapp_user_id = "whatsapp-other", whatsapp_phone_number = SecretStr("+15550000000"),  # ruff: ignore[line-too-long]
        ))

    def __save_private_chat(self):
        return self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = str(self.owner.telegram_user_id)))

    def test_connect_response_describes_the_owner(self):
        response = self.controller.connect(stubs.api.cli_connect_payload(connect_key = self.owner.connect_key))

        self.assertTrue(response.token)
        self.assertEqual(response.expires_at.utcoffset(), timedelta(0))
        self.assertEqual(response.user_id, self.owner.id.hex)
        self.assertEqual(response.user_display_name, self.owner.full_name)
        self.assertEqual(response.credit_balance, self.owner.credit_balance)

    def test_connect_display_name_falls_back_to_handle_then_id(self):
        base = dict(
            id = None, full_name = None, telegram_username = None, telegram_chat_id = None, telegram_user_id = None,
            whatsapp_user_id = None, whatsapp_phone_number = None,
        )
        cases = {
            "telegram username": (dict(telegram_username = "tg_handle"), "tg_handle"),
            "whatsapp phone": (dict(whatsapp_phone_number = SecretStr("+15551234567")), "+15551234567"),
            "user id": ({}, None),
        }
        for index, (name, (fields, expected)) in enumerate(cases.items()):
            with self.subTest(name = name):
                user = self.di.user_repo.save(stubs.domain.user(**(base | fields | dict(connect_key = f"NAME-KEY-{index}"))))
                user_di = self.di.clone(invoker_id = user.id.hex)
                user_di.inject_invoker(user)

                response = user_di.cli_controller.connect(stubs.api.cli_connect_payload())

                self.assertEqual(response.user_display_name, expected or user.id.hex)

    def test_every_generation_but_the_current_one_is_revoked(self):
        self.owner = self.di.user_repo.save(replace(self.owner, cli_token_generation = 3))
        self.controller.require_valid_cli_token(self.__claims(generation = 3))

        for generation in (0, 2, 4):
            with self.subTest(generation = generation):
                with self.assertRaises(AuthenticationError) as context:
                    self.controller.require_valid_cli_token(self.__claims(generation = generation))
                self.assertEqual(context.exception.error_code, CLI_ACCESS_REVOKED)

    def test_merged_away_owner_is_not_found(self):
        with self.assertRaises(NotFoundError) as context:
            self.controller.require_valid_cli_token(self.__claims(user_id = uuid4().hex))

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)

    def test_revoke_all_invalidates_earlier_tokens_and_keeps_the_connect_key(self):
        earlier = self.__claims()

        self.controller.revoke_all(self.owner.id.hex)

        with self.assertRaises(AuthenticationError) as context:
            self.controller.require_valid_cli_token(earlier)
        self.assertEqual(context.exception.error_code, CLI_ACCESS_REVOKED)
        self.controller.require_valid_cli_token(self.__claims(generation = earlier.generation + 1))
        self.assertEqual(self.__stored_owner().connect_key, self.owner.connect_key)

    def test_another_users_id_is_rejected_and_changes_nothing(self):
        other = self.__save_other_user()
        hostname = self.__claims().hostname
        calls = {
            "revoke all": lambda: self.controller.revoke_all(other.id.hex),
            "notify user": lambda: self.controller.notify_user(hostname, other.id.hex, stubs.api.cli_notify_user_payload()),
        }
        for name, call in calls.items():
            with self.subTest(name = name):
                with self.assertRaises(AuthorizationError) as context:
                    call()
                self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

        self.assertEqual(self.__stored_owner().cli_token_generation, 0)
        self.assertEqual(self.di.authorization_service.validate_user(other.id).cli_token_generation, 0)

    def test_list_chats_maps_the_authorized_chats(self):
        chat = self.__save_private_chat()

        self.assertEqual(
            self.controller.list_chats(),
            [CliChatResponse(chat_id = chat.chat_id.hex, platform = "telegram", title = chat.title, is_private = True)],
        )

    def test_notify_user_reports_the_chat_and_the_balance(self):
        chat = self.__save_private_chat()

        response = self.controller.notify_user(self.__claims().hostname, self.owner.id.hex, stubs.api.cli_notify_user_payload())

        self.assertEqual(response.chat_id, chat.chat_id.hex)
        self.assertEqual(response.platform, "telegram")
        self.assertTrue(response.is_private)
        self.assertEqual(response.credit_balance, self.owner.credit_balance)

    def test_notify_chat_prefixes_the_hostname_from_the_claims(self):
        group = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(), external_id = "group-1", title = "Team", is_private = False,
        ))
        self.telegram.members[("group-1", str(self.owner.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        response = self.controller.notify_chat(self.__claims().hostname, group.chat_id.hex, stubs.api.cli_notify_chat_payload())

        self.assertEqual(response.chat_id, group.chat_id.hex)
        sent = [message["text"] for message in self.telegram.get_sent_messages("group-1")]
        self.assertEqual(sent, ["🖥️  [mark_johnson@build-box-01] Build finished"])

    def test_unsupported_platform_is_a_validation_error(self):
        with self.assertRaises(ValidationError) as context:
            self.controller.notify_user(
                self.__claims().hostname, self.owner.id.hex, stubs.api.cli_notify_user_payload(platform = "github"),
            )

        self.assertEqual(context.exception.error_code, INVALID_PLATFORM)

    def test_owner_who_is_not_onboarded_cannot_notify(self):
        self.owner = self.di.user_repo.save(replace(self.owner, is_on_waitlist = True, is_invited_to_start = False))
        self.di.inject_invoker(self.owner)
        calls = {
            "notify user": lambda: self.controller.notify_user(
                self.__claims().hostname, self.owner.id.hex, stubs.api.cli_notify_user_payload(),
            ),
            "notify chat": lambda: self.controller.notify_chat(
                self.__claims().hostname, uuid4().hex, stubs.api.cli_notify_chat_payload(),
            ),
        }
        for name, call in calls.items():
            with self.subTest(name = name):
                with self.assertRaises(AuthorizationError) as context:
                    call()
                self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)
