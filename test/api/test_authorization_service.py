from typing import cast
from unittest import TestCase
from uuid import UUID

import stubs
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from util.di_utils import di_for_tests

from api.authorization_service import AuthorizationService
from di.di import DI
from features.users.user import User
from util.config import config
from util.error_codes import NOT_CHAT_ADMIN, NOT_CHAT_MEMBER, WAITLIST_ACCOUNT_NOT_ACTIVE, WAITLIST_INVITED_POLICIES_REQUIRED
from util.errors import AuthorizationError, NotFoundError, ValidationError


class AuthorizationServiceTest(TestCase):

    di: DI
    service: AuthorizationService
    user: User
    bot: FakeTelegramBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.authorization_service
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)

    def test_validate_chat_success_with_string(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config())

        for chat_id in (chat.chat_id.hex, chat.chat_id):
            with self.subTest(chat_id = chat_id):
                self.assertEqual(self.service.validate_chat(chat_id), chat)

    def test_validate_chat_success_with_instance(self):
        chat = stubs.domain.chat_config()

        self.assertIs(self.service.validate_chat(chat), chat)

    def test_validate_chat_failure_malformed_id(self):
        with self.assertRaises(ValidationError) as context:
            self.service.validate_chat("wrong_chat_id")

        self.assertIn("Malformed chat ID 'wrong_chat_id'", str(context.exception))

    def test_validate_user_success_with_hex_string(self):
        self.assertEqual(self.service.validate_user(self.user.id.hex), self.user)

    def test_validate_user_success_with_uuid(self):
        self.assertEqual(self.service.validate_user(self.user.id), self.user)

    def test_validate_user_success_with_instance(self):
        self.assertIs(self.service.validate_user(self.user), self.user)

    def test_validate_user_failure_malformed_id(self):
        with self.assertRaises(ValidationError) as context:
            self.service.validate_user("wrong_user_id")

        self.assertIn("Malformed user ID 'wrong_user_id'", str(context.exception))

    def test_validate_user_failure_user_not_found(self):
        with self.assertRaises(NotFoundError) as context:
            self.service.validate_user("00000000000000000000000000000000")

        self.assertIn("User '00000000000000000000000000000000' not found", str(context.exception))

    def test_authorize_for_user_success(self):
        self.assertEqual(self.service.authorize_for_user(self.user, self.user.id.hex), self.user)

    def test_authorize_for_user_failure_different_user(self):
        other_user = self.di.user_repo.save(stubs.domain.user(
            id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000002"), telegram_user_id = None, whatsapp_user_id = None, connect_key = "OTHER-USER",  # ruff: ignore[line-too-long]
        ))

        with self.assertRaises(AuthorizationError) as context:
            self.service.authorize_for_user(self.user, other_user.id.hex)

        self.assertIn("is not the allowed user", str(context.exception))

    def test_get_authorized_chats_success_user_is_admin(self):
        chats = [
            self.di.chat_config_repo.save(stubs.domain.chat_config(
                chat_id = UUID(f"aaaaaaaa-aaaa-4aaa-8aaa-{number:012d}"), external_id = str(number), is_private = False,
            ))
            for number in (10, 11, 12)
        ]
        for chat, member in zip(chats, (
            stubs.external.telegram_chat_administrator(),
            stubs.external.telegram_chat_member(),
            stubs.external.telegram_chat_owner(),
        ), strict = True):
            self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = member

        admin_chats = self.service.get_authorized_chats(self.user)

        self.assertCountEqual([chat.chat_id for chat in admin_chats], [chats[0].chat_id, chats[2].chat_id])

    def test_get_authorized_chats_success_user_administers_multiple_chats(self):
        own_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.user.telegram_chat_id))
        group = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000022"), external_id = "group", is_private = False,
        ))
        self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000023"), external_id = "someone-else",
        ))
        self.bot.members[(group.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        admin_chats = self.service.get_authorized_chats(self.user)

        self.assertEqual([chat.chat_id for chat in admin_chats], [own_chat.chat_id, group.chat_id])

    def test_get_authorized_chats_user_no_telegram_id(self):
        user = stubs.domain.user(telegram_chat_id = None, telegram_user_id = None)
        self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))

        self.assertEqual(self.service.get_authorized_chats(user), [])

    def test_get_authorized_chats_sorting_order(self):
        group_z = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000003"), external_id = "group-z", title = "Z Group", is_private = False,  # ruff: ignore[line-too-long]
        ))
        private_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = self.user.telegram_chat_id))
        group_no_title = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000005"), external_id = "untitled", title = None, is_private = False,
        ))
        group_a = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000004"), external_id = "group-a", title = "A Group", is_private = False,  # ruff: ignore[line-too-long]
        ))
        for chat in (group_z, group_no_title, group_a):
            self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        admin_chats = self.service.get_authorized_chats(self.user)

        self.assertEqual([chat.chat_id for chat in admin_chats], [
            private_chat.chat_id, group_no_title.chat_id, group_a.chat_id, group_z.chat_id,
        ])

    def test_authorize_for_user_success_with_uuid(self):
        self.assertEqual(self.service.authorize_for_user(self.user, self.user.id), self.user)

    def test_authorize_for_user_success_with_instance(self):
        self.assertIs(self.service.authorize_for_user(self.user, self.user), self.user)

    def test_require_user_is_chat_ready_success(self):
        self.assertEqual(self.service.require_user_is_chat_ready(self.user), self.user)

    def test_require_user_is_chat_ready_waitlist_requires_activation(self):
        user = stubs.domain.user(is_on_waitlist = True, is_invited_to_start = False, are_policies_accepted = False)

        with self.assertRaises(AuthorizationError) as context:
            self.service.require_user_is_chat_ready(user)

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)

    def test_require_user_is_chat_ready_invited_requires_policies(self):
        user = stubs.domain.user(is_on_waitlist = True, are_policies_accepted = False)

        with self.assertRaises(AuthorizationError) as context:
            self.service.require_user_is_chat_ready(user)

        self.assertEqual(context.exception.error_code, WAITLIST_INVITED_POLICIES_REQUIRED)

    def test_require_user_is_chat_ready_non_waitlisted_requires_policies(self):
        user = stubs.domain.user(are_policies_accepted = False)

        with self.assertRaises(AuthorizationError) as context:
            self.service.require_user_is_chat_ready(user)

        self.assertEqual(context.exception.error_code, WAITLIST_INVITED_POLICIES_REQUIRED)

    def test_require_waitlisted_user_can_activate_when_invited(self):
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 1
        user = self.di.user_repo.save(stubs.domain.user(is_on_waitlist = True, are_policies_accepted = False))

        self.assertEqual(self.service.require_waitlisted_user_can_activate(user), user)

    def test_require_waitlisted_user_can_activate_with_available_capacity(self):
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 2
        user = self.di.user_repo.save(stubs.domain.user(
            is_on_waitlist = True, is_invited_to_start = False, are_policies_accepted = False,
        ))

        self.assertEqual(self.service.require_waitlisted_user_can_activate(user), user)

    def test_require_waitlisted_user_can_activate_denied_without_invite_or_capacity(self):
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 1
        user = self.di.user_repo.save(stubs.domain.user(
            is_on_waitlist = True, is_invited_to_start = False, are_policies_accepted = False,
        ))

        with self.assertRaises(AuthorizationError) as context:
            self.service.require_waitlisted_user_can_activate(user)

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)

    def test_validate_chat_admin_success_when_admin(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        self.assertEqual(self.service.validate_chat_admin(self.user, chat), chat)

    def test_validate_chat_admin_denied_when_not_admin(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.di.chat_membership_service.save(stubs.domain.chat_membership(use_about_me = False, use_custom_prompt = False))
        self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()

        with self.assertRaises(AuthorizationError) as context:
            self.service.validate_chat_admin(self.user, chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)

    def test_update_chat_authorization_returns_current_membership(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        result = self.service.update_chat_authorization(self.user, chat)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertTrue(result.is_admin)

    def test_update_chat_authorization_propagates_authorization_error(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member_left()

        with self.assertRaises(AuthorizationError) as context:
            self.service.update_chat_authorization(self.user, chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)

    def test_update_all_chat_authorizations_returns_current_memberships(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.bot.members[(chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()

        result = self.service.update_all_chat_authorizations(self.user)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, self.user.id)
        self.assertEqual(result[0].chat_id, chat.chat_id)
        self.assertTrue(result[0].is_admin)
