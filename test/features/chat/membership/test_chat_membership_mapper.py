import unittest
from uuid import UUID

import stubs

from features.chat.membership.chat_membership_mapper import db, domain


class ChatMembershipMapperTest(unittest.TestCase):

    user_id: UUID
    chat_id: UUID

    def setUp(self):
        self.user_id = UUID("11111111-1111-1111-1111-111111111111")
        self.chat_id = UUID("22222222-2222-2222-2222-222222222222")

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_membership_db(
            user_id = self.user_id,
            chat_id = self.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = True,
        )

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, self.user_id)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertTrue(result.is_admin)
        self.assertFalse(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_membership(
            user_id = self.user_id,
            chat_id = self.chat_id,
            is_admin = False,
            use_about_me = True,
            use_custom_prompt = False,
        )

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, self.user_id)
        self.assertEqual(result.chat_id, self.chat_id)
        self.assertFalse(result.is_admin)
        self.assertTrue(result.use_about_me)
        self.assertFalse(result.use_custom_prompt)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = stubs.domain.chat_membership(
            user_id = self.user_id,
            chat_id = self.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = False,
        )

        result = domain(db(original))

        self.assertEqual(result.user_id, original.user_id)
        self.assertEqual(result.chat_id, original.chat_id)
        self.assertEqual(result.is_admin, original.is_admin)
        self.assertEqual(result.use_about_me, original.use_about_me)
        self.assertEqual(result.use_custom_prompt, original.use_custom_prompt)
