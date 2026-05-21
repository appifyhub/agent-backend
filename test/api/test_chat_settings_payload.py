import unittest

from pydantic import ValidationError

from api.model.chat_config_payload import ChatConfigPayload
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.user_chat_config_payload import UserChatConfigPayload


class ChatSettingsPayloadTest(unittest.TestCase):

    def test_basic_creation_with_both_blocks(self):
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "Spanish",
                language_iso_code = "es",
                reply_chance_percent = 75,
                release_notifications = "all",
                media_mode = "photo",
            ),
            user_chat_config = UserChatConfigPayload(
                use_about_me = True,
                use_custom_prompt = True,
                max_output_tokens = 2000,
                max_chat_history_depth = 30,
                max_iterations = 20,
            ),
        )

        self.assertIsNotNone(payload.chat_config)
        self.assertEqual(payload.chat_config.language_name, "Spanish")
        self.assertEqual(payload.chat_config.language_iso_code, "es")
        self.assertEqual(payload.chat_config.reply_chance_percent, 75)
        self.assertEqual(payload.chat_config.release_notifications, "all")
        self.assertEqual(payload.chat_config.media_mode, "photo")
        self.assertIsNotNone(payload.user_chat_config)
        self.assertTrue(payload.user_chat_config.use_about_me)
        self.assertTrue(payload.user_chat_config.use_custom_prompt)

    def test_creation_with_only_user_chat_config(self):
        payload = ChatSettingsPayload(
            user_chat_config = UserChatConfigPayload(
                use_about_me = False,
                use_custom_prompt = True,
                max_output_tokens = 2000,
                max_chat_history_depth = 30,
                max_iterations = 20,
            ),
        )

        self.assertIsNone(payload.chat_config)
        self.assertIsNotNone(payload.user_chat_config)
        self.assertFalse(payload.user_chat_config.use_about_me)
        self.assertTrue(payload.user_chat_config.use_custom_prompt)

    def test_creation_with_only_chat_config(self):
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "English",
                language_iso_code = "en",
                reply_chance_percent = 50,
                release_notifications = "major",
                media_mode = "all",
            ),
        )

        self.assertIsNotNone(payload.chat_config)
        self.assertIsNone(payload.user_chat_config)

    def test_empty_payload_validates_at_pydantic_level(self):
        # both fields are optional at the pydantic level — empty body parses fine
        payload = ChatSettingsPayload()
        self.assertIsNone(payload.chat_config)
        self.assertIsNone(payload.user_chat_config)
        # the controller is responsible for rejecting the empty case at runtime

    def test_string_trimming_validation(self):
        config = ChatConfigPayload(
            language_name = "  English  ",
            language_iso_code = "\ten\n",
            reply_chance_percent = 50,
            release_notifications = "  none  ",
            media_mode = "  file  ",
        )

        self.assertEqual(config.language_name, "English")
        self.assertEqual(config.language_iso_code, "en")
        self.assertEqual(config.release_notifications, "none")
        self.assertEqual(config.media_mode, "file")

    def test_empty_strings_after_trimming(self):
        config = ChatConfigPayload(
            language_name = "   ",
            language_iso_code = "",
            reply_chance_percent = 25,
            release_notifications = "\t\n",
            media_mode = "\t\n",
        )

        self.assertEqual(config.language_name, "")
        self.assertEqual(config.language_iso_code, "")
        self.assertEqual(config.release_notifications, "")
        self.assertEqual(config.media_mode, "")

    def test_reply_chance_validation_valid_values(self):
        for percent in (0, 50, 100):
            config = ChatConfigPayload(
                language_name = "English",
                language_iso_code = "en",
                reply_chance_percent = percent,
                release_notifications = "all",
                media_mode = "photo",
            )
            self.assertEqual(config.reply_chance_percent, percent)

    def test_reply_chance_validation_invalid_values(self):
        for percent in (-1, 101, 200):
            with self.assertRaises(ValidationError) as context:
                ChatConfigPayload(
                    language_name = "English",
                    language_iso_code = "en",
                    reply_chance_percent = percent,
                    release_notifications = "all",
                    media_mode = "photo",
                )
            self.assertIn("Reply chance percent must be between 0 and 100", str(context.exception))
