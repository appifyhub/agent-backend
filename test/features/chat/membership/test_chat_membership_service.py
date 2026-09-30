import unittest
from dataclasses import replace
from typing import cast
from uuid import UUID

import stubs
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership_repo import ChatMembershipRepository
from features.chat.membership.chat_membership_service import ChatMembershipService
from features.users.user import User
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, NOT_CHAT_MEMBER
from util.errors import AuthorizationError, ExternalServiceError


class ChatMembershipServiceTest(unittest.TestCase):

    di: DI
    repo: ChatMembershipRepository
    bot: FakeTelegramBotAPI
    member_key: tuple[str, str]
    service: ChatMembershipService
    user: User
    chat: ChatConfig

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.repo = self.di.chat_membership_repo
        self.user = stubs.domain.user()
        self.chat = stubs.domain.chat_config(is_private = False)
        self.member_key = (self.chat.external_id, str(self.user.telegram_user_id))
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member()
        self.service = self.di.chat_membership_service

    # === get ===

    def test_get_returns_none_when_missing(self):
        result = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNone(result)

    def test_get_returns_existing_row(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = False,
                max_output_tokens = 1000,
                max_chat_history_depth = 10,
                max_iterations = 7,
            ),
        )

        result = self.service.get(self.user.id, self.chat.chat_id)

        self.assertIsNotNone(result)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 1000)
        self.assertEqual(result.max_chat_history_depth, 10)
        self.assertEqual(result.max_iterations, 7)

    # === get_all_for_user ===

    def test_get_all_for_user_returns_empty_when_none(self):
        result = self.service.get_all_for_user(self.user.id)
        self.assertEqual(len(result), 0)

    def test_get_all_for_user_returns_all_rows(self):
        second_chat = stubs.domain.chat_config(chat_id = UUID("33333333-3333-4333-8333-c33333333333"))
        repo = self.di.chat_membership_repo
        repo.save(stubs.domain.chat_membership(user_id = self.user.id, chat_id = self.chat.chat_id))
        repo.save(stubs.domain.chat_membership(user_id = self.user.id, chat_id = second_chat.chat_id))

        result = self.service.get_all_for_user(self.user.id)

        self.assertEqual(len(result), 2)
        chat_ids = {r.chat_id for r in result}
        self.assertIn(self.chat.chat_id, chat_ids)
        self.assertIn(second_chat.chat_id, chat_ids)

    # === save ===

    def test_save_creates_new_row(self):
        membership = stubs.domain.chat_membership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = False,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )

        result = self.service.save(membership)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 500)
        self.assertEqual(result.max_chat_history_depth, 5)
        self.assertEqual(result.max_iterations, 3)

    def test_save_upserts_existing_row(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
            ),
        )

        result = self.service.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                max_output_tokens = 8000,
                max_chat_history_depth = 50,
                max_iterations = 10,
            ),
        )

        self.assertTrue(result.is_admin)
        self.assertEqual(result.max_output_tokens, 8000)
        self.assertEqual(result.max_chat_history_depth, 50)
        self.assertEqual(result.max_iterations, 10)
        fetched = self.service.get(self.user.id, self.chat.chat_id)
        self.assertTrue(fetched.is_admin)
        self.assertEqual(fetched.max_output_tokens, 8000)

    # === sync ===

    def test_sync_returns_existing_unchanged_when_admin_matches(self):
        existing = self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                use_about_me = False,
                use_custom_prompt = False,
            ),
        )
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member()

        result = self.service.sync(self.user, self.chat)

        self.assertEqual(result.user_id, existing.user_id)
        self.assertFalse(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertEqual(self.repo.get(self.user.id, self.chat.chat_id), existing)

    def test_sync_refreshes_admin_status_on_existing(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                use_about_me = False,
                use_custom_prompt = False,
                max_output_tokens = 500,
                max_chat_history_depth = 5,
                max_iterations = 3,
            ),
        )
        self.bot.members[self.member_key] = stubs.external.telegram_chat_owner()

        result = self.service.sync(self.user, self.chat)

        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertFalse(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 500)
        self.assertEqual(result.max_chat_history_depth, 5)
        self.assertEqual(result.max_iterations, 3)
        self.assertEqual(self.service.get(self.user.id, self.chat.chat_id), result)

    def test_sync_creates_with_admin_access(self):
        self.bot.members[self.member_key] = stubs.external.telegram_chat_owner()

        result = self.service.sync(self.user, self.chat)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertTrue(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(self.repo.get(self.user.id, self.chat.chat_id), result)

    def test_sync_creates_with_member_access(self):
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member()

        result = self.service.sync(self.user, self.chat)

        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNotNone(stored)

    def test_ensure_for_inbound_returns_cached_membership_without_platform_lookup(self):
        existing = self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = False,
            ),
        )
        self.bot.members.clear()

        result = self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(result.user_id, existing.user_id)
        self.assertEqual(result.chat_id, existing.chat_id)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertEqual(self.repo.get(self.user.id, self.chat.chat_id), existing)

    def test_ensure_for_inbound_creates_missing_membership(self):
        self.bot.members[self.member_key] = stubs.external.telegram_chat_owner()

        result = self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertTrue(result.is_admin)
        self.assertEqual(self.repo.get(self.user.id, self.chat.chat_id), result)

    def test_ensure_for_inbound_rejects_non_participant_without_creating_membership(self):
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member_left()

        with self.assertRaises(AuthorizationError) as context:
            self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
        self.assertIsNone(self.repo.get(self.user.id, self.chat.chat_id))

    def test_ensure_for_inbound_rejects_membership_when_platform_lookup_fails(self):
        error = ExternalServiceError("Platform access unavailable", EXTERNAL_EMPTY_RESPONSE)
        self.bot.members[self.member_key] = error

        with self.assertRaises(AuthorizationError) as context:
            self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
        self.assertIsNone(self.repo.get(self.user.id, self.chat.chat_id))

    def test_sync_creates_with_owner_access(self):
        self.chat = replace(self.chat, is_private = True, external_id = str(self.user.telegram_user_id))
        self.bot.members.clear()

        result = self.service.sync(self.user, self.chat)

        self.assertTrue(result.is_admin)
        self.assertEqual(self.repo.get(self.user.id, self.chat.chat_id), result)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNotNone(stored)

    def test_sync_rejects_non_participant(self):
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member_left()

        with self.assertRaises(AuthorizationError) as context:
            self.service.sync(self.user, self.chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNone(stored)

    def test_sync_allows_existing_row_when_access_is_none(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
            ),
        )
        self.bot.members[self.member_key] = stubs.external.telegram_chat_member_left()

        result = self.service.sync(self.user, self.chat)

        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)

    # === refresh_chat_memberships ===

    def test_refresh_chat_memberships_promotes_new_admin(self):
        result = self.service.refresh_chat_memberships(self.user, [self.chat])

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_admin)

    def test_refresh_chat_memberships_preserves_preferences_on_promote(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                use_about_me = False,
                use_custom_prompt = False,
                max_output_tokens = 500,
                max_chat_history_depth = 5,
                max_iterations = 3,
            ),
        )

        result = self.service.refresh_chat_memberships(self.user, [self.chat])

        self.assertTrue(result[0].is_admin)
        self.assertFalse(result[0].use_about_me)
        self.assertFalse(result[0].use_custom_prompt)
        self.assertEqual(result[0].max_output_tokens, 500)
        self.assertEqual(result[0].max_chat_history_depth, 5)
        self.assertEqual(result[0].max_iterations, 3)

    def test_refresh_chat_memberships_demotes_stale_admin(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
            ),
        )

        result = self.service.refresh_chat_memberships(self.user, [])

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_admin)
        self.assertTrue(result[0].use_about_me)
        self.assertTrue(result[0].use_custom_prompt)

    def test_refresh_chat_memberships_preserves_already_correct_admin_membership(self):
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
            ),
        )

        self.service.refresh_chat_memberships(self.user, [self.chat])

        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertTrue(stored.is_admin)

    def test_refresh_chat_memberships_creates_missing_admin_row_with_defaults(self):
        result = self.service.refresh_chat_memberships(self.user, [self.chat])

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_admin)
        self.assertTrue(result[0].use_about_me)
        self.assertTrue(result[0].use_custom_prompt)

    def test_refresh_chat_memberships_handles_multiple_chats(self):
        second_chat = stubs.domain.chat_config(chat_id = UUID("33333333-3333-4333-8333-c33333333333"))
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = self.user.id, chat_id = self.chat.chat_id, is_admin = True),
        )
        self.di.chat_membership_repo.save(
            stubs.domain.chat_membership(user_id = self.user.id, chat_id = second_chat.chat_id),
        )
        result = self.service.refresh_chat_memberships(self.user, [second_chat])

        by_chat = {m.chat_id: m for m in result}
        self.assertFalse(by_chat[self.chat.chat_id].is_admin)
        self.assertTrue(by_chat[second_chat.chat_id].is_admin)

    def test_refresh_chat_memberships_with_no_admin_chats_returns_empty(self):
        result = self.service.refresh_chat_memberships(self.user, [])

        self.assertEqual(len(result), 0)
