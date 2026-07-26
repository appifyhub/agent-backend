import unittest
from datetime import datetime
from unittest.mock import Mock

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership
from features.chat.membership.chat_membership_service import ChatMembershipService
from features.integrations.platform_bot_sdk import ChatAccess
from features.users.user import User
from util.error_codes import NOT_CHAT_MEMBER
from util.errors import AuthorizationError


class ChatMembershipServiceTest(unittest.TestCase):

    sql: SQLUtil
    mock_di: DI
    service: ChatMembershipService
    user: User
    chat: ChatConfig

    def setUp(self):
        self.sql = SQLUtil()
        self.user = self.sql.user_repo().save(
            User(
                full_name = "Test User",
                telegram_username = "testuser",
                telegram_chat_id = "chat_ext_1",
                telegram_user_id = 1,
                open_ai_key = SecretStr("key"),
                group = UserDB.Group.standard,
                created_at = datetime.now().date(),
            ),
        )
        self.chat = self.sql.chat_config_repo().save(
            ChatConfig(
                external_id = "chat_ext_1",
                chat_type = ChatConfigDB.ChatType.telegram,
                is_private = True,
            ),
        )
        self.mock_sdk = Mock()
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.member
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_repo = self.sql.chat_membership_repo()
        self.mock_di.platform_bot_sdk.return_value = self.mock_sdk
        self.service = ChatMembershipService(self.mock_di)

    def tearDown(self):
        self.sql.end_session()

    # === get ===

    def test_get_returns_none_when_missing(self):
        result = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNone(result)

    def test_get_returns_existing_row(self):
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = False,
                use_custom_prompt = True,
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
        second_chat = self.sql.chat_config_repo().save(
            ChatConfig(
                external_id = "chat_ext_2",
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
        )
        repo = self.sql.chat_membership_repo()
        repo.save(ChatMembership(user_id = self.user.id, chat_id = self.chat.chat_id))
        repo.save(ChatMembership(user_id = self.user.id, chat_id = second_chat.chat_id))

        result = self.service.get_all_for_user(self.user.id)

        self.assertEqual(len(result), 2)
        chat_ids = {r.chat_id for r in result}
        self.assertIn(self.chat.chat_id, chat_ids)
        self.assertIn(second_chat.chat_id, chat_ids)

    # === save ===

    def test_save_creates_new_row(self):
        membership = ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = True,
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
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = False,
                max_output_tokens = 500,
                max_chat_history_depth = 5,
                max_iterations = 3,
            ),
        )

        result = self.service.save(
            ChatMembership(
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
        existing = self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = False,
                use_about_me = False,
                use_custom_prompt = False,
            ),
        )
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.member

        result = self.service.sync(self.user, self.chat)

        self.assertEqual(result.user_id, existing.user_id)
        self.assertFalse(result.is_admin)
        self.assertFalse(result.use_about_me)

    def test_sync_refreshes_admin_status_on_existing(self):
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = False,
                use_about_me = False,
                use_custom_prompt = False,
            ),
        )
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.admin

        result = self.service.sync(self.user, self.chat)

        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertFalse(result.use_custom_prompt)

    def test_sync_creates_with_admin_access(self):
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.admin

        result = self.service.sync(self.user, self.chat)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertTrue(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.mock_sdk.resolve_chat_access.assert_called_once_with(self.chat, self.user)

    def test_sync_creates_with_member_access(self):
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.member

        result = self.service.sync(self.user, self.chat)

        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNotNone(stored)

    def test_sync_resolves_platform_access_before_membership_query_without_rollback(self):
        events = []
        repo = self.mock_di.chat_membership_repo
        original_get = repo.get

        def get_membership(user_id, chat_id):
            events.append("get")
            return original_get(user_id, chat_id)

        def rollback_session():
            events.append("rollback")

        def resolve_access(chat, user):
            events.append("resolve")
            return ChatAccess.member

        repo.get = Mock(side_effect = get_membership)
        self.mock_di.rollback_db_session.side_effect = rollback_session
        self.mock_sdk.resolve_chat_access.side_effect = resolve_access

        result = self.service.sync(self.user, self.chat)

        self.assertIsNotNone(result)
        self.assertEqual(events, ["resolve", "get"])
        self.mock_di.rollback_db_session.assert_not_called()

    def test_ensure_for_inbound_returns_cached_membership_without_platform_lookup(self):
        existing = self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = False,
            ),
        )
        self.mock_di.rollback_db_session.reset_mock()

        result = self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(result.user_id, existing.user_id)
        self.assertEqual(result.chat_id, existing.chat_id)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.mock_sdk.resolve_chat_access.assert_not_called()
        self.mock_di.rollback_db_session.assert_called_once_with()

    def test_ensure_for_inbound_live_syncs_missing_membership_after_rolling_back_read(self):
        events = []
        repo = self.mock_di.chat_membership_repo
        original_get = repo.get
        original_save = repo.save

        def get_membership(user_id, chat_id):
            events.append("get")
            return original_get(user_id, chat_id)

        def save_membership(membership):
            events.append("save")
            return original_save(membership)

        def rollback_session():
            events.append("rollback")

        def resolve_access(chat, user):
            events.append("resolve")
            return ChatAccess.admin

        repo.get = Mock(side_effect = get_membership)
        repo.save = Mock(side_effect = save_membership)
        self.mock_di.rollback_db_session.side_effect = rollback_session
        self.mock_sdk.resolve_chat_access.side_effect = resolve_access

        result = self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertTrue(result.is_admin)
        self.assertEqual(events, ["get", "rollback", "resolve", "get", "save", "rollback"])
        self.mock_sdk.resolve_chat_access.assert_called_once_with(self.chat, self.user)

    def test_ensure_for_inbound_rolls_back_when_live_sync_rejects_missing_membership(self):
        events = []
        repo = self.mock_di.chat_membership_repo
        original_get = repo.get

        def get_membership(user_id, chat_id):
            events.append("get")
            return original_get(user_id, chat_id)

        def rollback_session():
            events.append("rollback")

        def resolve_access(chat, user):
            events.append("resolve")
            return None

        repo.get = Mock(side_effect = get_membership)
        self.mock_di.rollback_db_session.side_effect = rollback_session
        self.mock_sdk.resolve_chat_access.side_effect = resolve_access

        with self.assertRaises(AuthorizationError) as context:
            self.service.ensure_for_inbound(self.user, self.chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
        self.assertEqual(events, ["get", "rollback", "resolve", "get", "rollback"])

    def test_sync_creates_with_owner_access(self):
        self.mock_sdk.resolve_chat_access.return_value = ChatAccess.owner

        result = self.service.sync(self.user, self.chat)

        self.assertTrue(result.is_admin)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNotNone(stored)

    def test_sync_rejects_non_participant(self):
        self.mock_sdk.resolve_chat_access.return_value = None

        with self.assertRaises(AuthorizationError) as context:
            self.service.sync(self.user, self.chat)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)
        stored = self.service.get(self.user.id, self.chat.chat_id)
        self.assertIsNone(stored)

    def test_sync_allows_existing_row_when_access_is_none(self):
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = True,
                use_custom_prompt = True,
            ),
        )
        self.mock_sdk.resolve_chat_access.return_value = None

        result = self.service.sync(self.user, self.chat)

        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)

    # === refresh_chat_memberships ===

    def test_refresh_chat_memberships_promotes_new_admin(self):
        result = self.service.refresh_chat_memberships(self.user, [self.chat])

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_admin)

    def test_refresh_chat_memberships_preserves_preferences_on_promote(self):
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = False,
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
        self.sql.chat_membership_repo().save(
            ChatMembership(
                user_id = self.user.id,
                chat_id = self.chat.chat_id,
                is_admin = True,
                use_about_me = True,
                use_custom_prompt = True,
            ),
        )

        result = self.service.refresh_chat_memberships(self.user, [])

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_admin)
        self.assertTrue(result[0].use_about_me)
        self.assertTrue(result[0].use_custom_prompt)

    def test_refresh_chat_memberships_skips_already_correct_admin_row(self):
        self.sql.chat_membership_repo().save(
            ChatMembership(
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
        second_chat = self.sql.chat_config_repo().save(
            ChatConfig(
                external_id = "chat_ext_3",
                chat_type = ChatConfigDB.ChatType.telegram,
            ),
        )
        self.sql.chat_membership_repo().save(
            ChatMembership(user_id = self.user.id, chat_id = self.chat.chat_id, is_admin = True),
        )
        self.sql.chat_membership_repo().save(
            ChatMembership(user_id = self.user.id, chat_id = second_chat.chat_id, is_admin = False),
        )

        result = self.service.refresh_chat_memberships(self.user, [second_chat])

        by_chat = {m.chat_id: m for m in result}
        self.assertFalse(by_chat[self.chat.chat_id].is_admin)
        self.assertTrue(by_chat[second_chat.chat_id].is_admin)

    def test_refresh_chat_memberships_with_no_admin_chats_returns_empty(self):
        result = self.service.refresh_chat_memberships(self.user, [])

        self.assertEqual(len(result), 0)
