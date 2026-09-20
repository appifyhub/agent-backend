import unittest

import stubs

from api.mapper.chat_settings_api_mapper import domain_to_api


class ChatMapperTest(unittest.TestCase):

    def test_domain_to_api_conversion(self):
        chat = stubs.domain.chat_config(
            title = "Test Chat",
            is_private = False,
            reply_chance_percent = 75,
        )
        membership = stubs.domain.chat_membership(
            chat_id = chat.chat_id,
            is_admin = True,
            use_custom_prompt = False,
        )

        api = domain_to_api(chat, membership, is_own = True)

        # chat_config block
        self.assertEqual(api.chat_config.chat_id, chat.chat_id.hex)
        self.assertEqual(api.chat_config.title, chat.title)
        self.assertEqual(api.chat_config.platform, chat.chat_type.value)
        self.assertEqual(api.chat_config.language_iso_code, chat.language_iso_code)
        self.assertEqual(api.chat_config.language_name, chat.language_name)
        self.assertEqual(api.chat_config.reply_chance_percent, chat.reply_chance_percent)
        self.assertEqual(api.chat_config.release_notifications, chat.release_notifications.value)
        self.assertEqual(api.chat_config.media_mode, chat.media_mode.value)
        self.assertEqual(api.chat_config.is_private, chat.is_private)
        self.assertTrue(api.chat_config.is_own)
        self.assertTrue(api.chat_config.is_admin)

        # user_chat_config block
        self.assertTrue(api.user_chat_config.use_about_me)
        self.assertFalse(api.user_chat_config.use_custom_prompt)
        self.assertEqual(api.user_chat_config.max_output_tokens, 3500)
        self.assertEqual(api.user_chat_config.max_chat_history_depth, 30)
        self.assertEqual(api.user_chat_config.max_iterations, 20)

    def test_non_admin_member_mapping(self):
        chat = stubs.domain.chat_config(
            title = "Test Chat",
            is_private = False,
            reply_chance_percent = 75,
        )
        membership = stubs.domain.chat_membership(
            chat_id = chat.chat_id,
            use_about_me = False,
            use_custom_prompt = False,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )
        api = domain_to_api(chat, membership, is_own = False)

        self.assertFalse(api.chat_config.is_admin)
        self.assertFalse(api.chat_config.is_own)
        self.assertFalse(api.user_chat_config.use_about_me)
        self.assertFalse(api.user_chat_config.use_custom_prompt)
        self.assertEqual(api.user_chat_config.max_output_tokens, 500)
        self.assertEqual(api.user_chat_config.max_chat_history_depth, 5)
        self.assertEqual(api.user_chat_config.max_iterations, 3)
