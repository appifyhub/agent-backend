import unittest

import stubs

from features.chat.membership.chat_membership_mapper import db, domain


class ChatMembershipMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields(self):
        db_model = stubs.db.chat_membership_db()

        result = domain(db_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, db_model.user_id)
        self.assertEqual(result.chat_id, db_model.chat_id)
        self.assertEqual(result.is_admin, db_model.is_admin)
        self.assertEqual(result.use_about_me, db_model.use_about_me)
        self.assertEqual(result.use_custom_prompt, db_model.use_custom_prompt)

    def test_db_maps_all_fields(self):
        domain_model = stubs.domain.chat_membership()

        result = db(domain_model)

        self.assertIsNotNone(result)
        self.assertEqual(result.user_id, domain_model.user_id)
        self.assertEqual(result.chat_id, domain_model.chat_id)
        self.assertEqual(result.is_admin, domain_model.is_admin)
        self.assertEqual(result.use_about_me, domain_model.use_about_me)
        self.assertEqual(result.use_custom_prompt, domain_model.use_custom_prompt)

    def test_roundtrip_domain_to_db_to_domain(self):
        original = stubs.domain.chat_membership()

        result = domain(db(original))

        self.assertEqual(result.user_id, original.user_id)
        self.assertEqual(result.chat_id, original.chat_id)
        self.assertEqual(result.is_admin, original.is_admin)
        self.assertEqual(result.use_about_me, original.use_about_me)
        self.assertEqual(result.use_custom_prompt, original.use_custom_prompt)
