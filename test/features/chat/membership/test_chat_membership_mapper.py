import unittest
from uuid import UUID

import stubs

from features.chat.membership.chat_membership_mapper import db, domain


class ChatMembershipMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_roundtrip_preserves_all_default_values(self):
        original = stubs.domain.chat_membership()

        db_model = db(original)

        self.assertIsNotNone(db_model)
        self.assertEqual(db_model.user_id, original.user_id)
        self.assertEqual(db_model.chat_id, original.chat_id)
        self.assertEqual(db_model.is_admin, original.is_admin)
        self.assertEqual(db_model.use_about_me, original.use_about_me)
        self.assertEqual(db_model.use_custom_prompt, original.use_custom_prompt)
        self.assertEqual(db_model.split_messages, original.split_messages)
        self.assertEqual(db_model.max_output_tokens, original.max_output_tokens)
        self.assertEqual(db_model.max_chat_history_depth, original.max_chat_history_depth)
        self.assertEqual(db_model.max_iterations, original.max_iterations)

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, original.user_id)
        self.assertEqual(result.chat_id, original.chat_id)
        self.assertEqual(result.is_admin, original.is_admin)
        self.assertEqual(result.use_about_me, original.use_about_me)
        self.assertEqual(result.use_custom_prompt, original.use_custom_prompt)
        self.assertEqual(result.split_messages, original.split_messages)
        self.assertEqual(result.max_output_tokens, original.max_output_tokens)
        self.assertEqual(result.max_chat_history_depth, original.max_chat_history_depth)
        self.assertEqual(result.max_iterations, original.max_iterations)

    def test_roundtrip_preserves_all_non_default_values(self):
        original = stubs.domain.chat_membership(
            user_id = UUID(int = 1),
            chat_id = UUID(int = 2),
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = False,
            split_messages = False,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )

        db_model = db(original)

        self.assertIsNotNone(db_model)
        self.assertEqual(db_model.user_id, UUID(int = 1))
        self.assertEqual(db_model.chat_id, UUID(int = 2))
        self.assertTrue(db_model.is_admin)
        self.assertFalse(db_model.use_about_me)
        self.assertFalse(db_model.use_custom_prompt)
        self.assertFalse(db_model.split_messages)
        self.assertEqual(db_model.max_output_tokens, 500)
        self.assertEqual(db_model.max_chat_history_depth, 5)
        self.assertEqual(db_model.max_iterations, 3)

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, UUID(int = 1))
        self.assertEqual(result.chat_id, UUID(int = 2))
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertFalse(result.use_custom_prompt)
        self.assertFalse(result.split_messages)
        self.assertEqual(result.max_output_tokens, 500)
        self.assertEqual(result.max_chat_history_depth, 5)
        self.assertEqual(result.max_iterations, 3)
