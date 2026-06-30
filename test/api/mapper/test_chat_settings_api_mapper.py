import unittest
from uuid import UUID

from api.mapper.chat_settings_api_mapper import domain_to_api
from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership


class ChatMapperTest(unittest.TestCase):

    chat: ChatConfig
    membership: ChatMembership

    def setUp(self):
        self.chat = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "12345",
            title = "Test Chat",
            language_iso_code = "en",
            language_name = "English",
            reply_chance_percent = 75,
            is_private = False,
            release_notifications = ChatConfigDB.ReleaseNotifications.major,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.membership = ChatMembership(
            user_id = UUID(int = 2),
            chat_id = self.chat.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = False,
        )

    def test_domain_to_api_conversion(self):
        api = domain_to_api(self.chat, self.membership, is_own = True)

        # chat_config block
        self.assertEqual(api.chat_config.chat_id, self.chat.chat_id.hex)
        self.assertEqual(api.chat_config.title, self.chat.title)
        self.assertEqual(api.chat_config.platform, self.chat.chat_type.value)
        self.assertEqual(api.chat_config.language_iso_code, self.chat.language_iso_code)
        self.assertEqual(api.chat_config.language_name, self.chat.language_name)
        self.assertEqual(api.chat_config.reply_chance_percent, self.chat.reply_chance_percent)
        self.assertEqual(api.chat_config.release_notifications, self.chat.release_notifications.value)
        self.assertEqual(api.chat_config.media_mode, self.chat.media_mode.value)
        self.assertEqual(api.chat_config.is_private, self.chat.is_private)
        self.assertTrue(api.chat_config.is_own)
        self.assertTrue(api.chat_config.is_admin)

        # user_chat_config block
        self.assertTrue(api.user_chat_config.use_about_me)
        self.assertFalse(api.user_chat_config.use_custom_prompt)
        self.assertEqual(api.user_chat_config.max_output_tokens, 3500)
        self.assertEqual(api.user_chat_config.max_chat_history_depth, 30)
        self.assertEqual(api.user_chat_config.max_iterations, 20)

    def test_non_admin_member_mapping(self):
        membership = ChatMembership(
            user_id = UUID(int = 3),
            chat_id = self.chat.chat_id,
            is_admin = False,
            use_about_me = False,
            use_custom_prompt = False,
            max_output_tokens = 500,
            max_chat_history_depth = 5,
            max_iterations = 3,
        )
        api = domain_to_api(self.chat, membership, is_own = False)

        self.assertFalse(api.chat_config.is_admin)
        self.assertFalse(api.chat_config.is_own)
        self.assertFalse(api.user_chat_config.use_about_me)
        self.assertFalse(api.user_chat_config.use_custom_prompt)
        self.assertEqual(api.user_chat_config.max_output_tokens, 500)
        self.assertEqual(api.user_chat_config.max_chat_history_depth, 5)
        self.assertEqual(api.user_chat_config.max_iterations, 3)
