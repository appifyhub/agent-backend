import unittest

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.chat_config import ChatConfigSave
from db.schema.user import UserSave
from features.chat.membership.chat_membership import ChatMembership
from features.chat.membership.chat_membership_repo import ChatMembershipRepository


class ChatMembershipRepoTest(unittest.TestCase):

    sql: SQLUtil
    repo: ChatMembershipRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.chat_membership_repo()
        self.chat = self.sql.chat_config_crud().create(
            ChatConfigSave(external_id = "chat1", chat_type = ChatConfigDB.ChatType.telegram),
        )
        self.user = self.sql.user_crud().create(
            UserSave(
                full_name = "Test User",
                telegram_username = "testuser",
                telegram_chat_id = "123456",
                telegram_user_id = 123456,
                open_ai_key = SecretStr("test-key"),
                group = UserDB.Group.standard,
            ),
        )

    def tearDown(self):
        self.sql.end_session()

    def test_get_returns_none_when_missing(self):
        result = self.repo.get(self.user.id, self.chat.chat_id)

        self.assertIsNone(result)

    def test_save_creates_new_membership(self):
        membership = ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = False,
            use_about_me = True,
            use_custom_prompt = True,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )

        result = self.repo.save(membership)

        self.assertEqual(result.user_id, self.user.id)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 500)
        self.assertEqual(result.max_chat_history_depth, 5)
        self.assertEqual(result.max_iterations, 3)

    def test_get_returns_saved_membership(self):
        membership = ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = True,
            max_output_tokens = 1000,
            max_chat_history_depth = 10,
            max_iterations = 7,
        )
        self.repo.save(membership)

        result = self.repo.get(self.user.id, self.chat.chat_id)

        self.assertIsNotNone(result)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 1000)
        self.assertEqual(result.max_chat_history_depth, 10)
        self.assertEqual(result.max_iterations, 7)

    def test_save_upserts_existing_membership(self):
        original = ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = False,
            use_about_me = True,
            use_custom_prompt = True,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )
        self.repo.save(original)

        updated = ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = False,
            max_output_tokens = 8000,
            max_chat_history_depth = 50,
            max_iterations = 10,
        )
        result = self.repo.save(updated)

        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertFalse(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 8000)
        self.assertEqual(result.max_chat_history_depth, 50)
        self.assertEqual(result.max_iterations, 10)
        fetched = self.repo.get(self.user.id, self.chat.chat_id)
        self.assertTrue(fetched.is_admin)
        self.assertEqual(fetched.max_output_tokens, 8000)

    def test_get_all_for_user_returns_memberships(self):
        second_chat = self.sql.chat_config_crud().create(
            ChatConfigSave(external_id = "chat2", chat_type = ChatConfigDB.ChatType.telegram),
        )
        self.repo.save(ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = False,
            use_about_me = True,
            use_custom_prompt = True,
        ))
        self.repo.save(ChatMembership(
            user_id = self.user.id,
            chat_id = second_chat.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = False,
        ))

        results = self.repo.get_all_for_user(self.user.id)

        self.assertEqual(len(results), 2)
        chat_ids = {r.chat_id for r in results}
        self.assertIn(self.chat.chat_id, chat_ids)
        self.assertIn(second_chat.chat_id, chat_ids)

    def test_get_all_for_user_returns_empty_when_none(self):
        results = self.repo.get_all_for_user(self.user.id)

        self.assertEqual(len(results), 0)

    def test_get_all_for_chat_returns_memberships(self):
        second_user = self.sql.user_crud().create(
            UserSave(
                full_name = "Second User",
                telegram_username = "second",
                telegram_chat_id = "654321",
                telegram_user_id = 654321,
                open_ai_key = SecretStr("key2"),
                group = UserDB.Group.standard,
            ),
        )
        self.repo.save(ChatMembership(
            user_id = self.user.id,
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        ))
        self.repo.save(ChatMembership(
            user_id = second_user.id,
            chat_id = self.chat.chat_id,
            is_admin = False,
            use_about_me = False,
            use_custom_prompt = True,
        ))

        results = self.repo.get_all_for_chat(self.chat.chat_id)

        self.assertEqual(len(results), 2)
        user_ids = {r.user_id for r in results}
        self.assertIn(self.user.id, user_ids)
        self.assertIn(second_user.id, user_ids)
