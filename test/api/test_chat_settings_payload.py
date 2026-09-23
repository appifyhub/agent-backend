import unittest

import stubs
from pydantic import ValidationError


class ChatSettingsPayloadTest(unittest.TestCase):

    def test_basic_creation_with_both_blocks(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(
                language_name = "Spanish",
                language_iso_code = "es",
                reply_chance_percent = 75,
                release_notifications = "all",
            ),
            user_chat_config = stubs.api.user_chat_config_payload(),
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
        payload = stubs.api.chat_settings_payload(
            chat_config = None,
            user_chat_config = stubs.api.user_chat_config_payload(use_about_me = False),
        )

        self.assertIsNone(payload.chat_config)
        self.assertIsNotNone(payload.user_chat_config)
        self.assertFalse(payload.user_chat_config.use_about_me)
        self.assertTrue(payload.user_chat_config.use_custom_prompt)

    def test_creation_with_only_chat_config(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(
                reply_chance_percent = 50,
                media_mode = "all",
            ),
            user_chat_config = None,
        )

        self.assertIsNotNone(payload.chat_config)
        self.assertIsNone(payload.user_chat_config)

    def test_empty_payload_validates_at_pydantic_level(self):
        # both fields are optional at the pydantic level — empty body parses fine
        payload = stubs.api.chat_settings_payload(chat_config = None, user_chat_config = None)
        self.assertIsNone(payload.chat_config)
        self.assertIsNone(payload.user_chat_config)
        # the controller is responsible for rejecting the empty case at runtime

    def test_string_trimming_validation(self):
        config = stubs.api.chat_config_payload(
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
        config = stubs.api.chat_config_payload(
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
            config = stubs.api.chat_config_payload(
                reply_chance_percent = percent,
            )
            self.assertEqual(config.reply_chance_percent, percent)

    def test_reply_chance_validation_invalid_values(self):
        for percent in (-1, 101, 200):
            with self.assertRaises(ValidationError) as context:
                stubs.api.chat_config_payload(
                    reply_chance_percent = percent,
                )
            self.assertIn("Reply chance percent must be between 0 and 100", str(context.exception))
