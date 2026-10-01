import unittest
from typing import cast
from uuid import uuid4

import stubs
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_url_shortener import FakeUrlShortener
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.command_processor import (
    COMMAND_CONNECT,
    COMMAND_HELP,
    COMMAND_SETTINGS,
    COMMAND_START,
    CommandProcessor,
    is_known_command,
)
from features.integrations.integrations import resolve_agent_user
from util.error_codes import UNEXPECTED_ERROR
from util.errors import ExternalServiceError


class CommandProcessorTest(unittest.TestCase):

    di: DI
    processor: CommandProcessor
    api: FakeTelegramBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        shortener = cast(FakeUrlShortener, self.di.url_shortener("https://example.com/settings"))
        shortener.short_url = "https://example.com/settings?token=abc123"
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user(telegram_chat_id = "test_chat_id")))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = "test_chat_id")))
        self.processor = self.di.command_processor

    def test_empty_input(self):
        result = self.processor.execute("")
        self.assertEqual(result.status, "ignored")

    def test_non_command_input(self):
        result = self.processor.execute("This is not a command")
        self.assertEqual(result.status, "ignored")

    def test_is_known_command_rejects_empty_or_blank(self):
        self.assertFalse(is_known_command("", "the_agent"))
        self.assertFalse(is_known_command(None, "the_agent"))
        self.assertFalse(is_known_command("   ", "the_agent"))

    def test_is_known_command_rejects_non_slash_input(self):
        self.assertFalse(is_known_command("hello", "the_agent"))
        self.assertFalse(is_known_command(f"hi /{COMMAND_HELP}", "the_agent"))  # slash not first token

    def test_is_known_command_rejects_unknown_command(self):
        self.assertFalse(is_known_command("/notacommand", "the_agent"))
        self.assertFalse(is_known_command("/notacommand@the_agent", "the_agent"))

    def test_is_known_command_rejects_malformed_slash_tokens(self):
        self.assertFalse(is_known_command("/", "the_agent"))
        self.assertFalse(is_known_command("/@the_agent", "the_agent"))
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@", "the_agent"))  # empty tag part

    def test_is_known_command_accepts_all_supported_commands(self):
        for command in (COMMAND_START, COMMAND_SETTINGS, COMMAND_HELP, COMMAND_CONNECT):
            self.assertTrue(is_known_command(f"/{command}", "the_agent"))
            self.assertTrue(is_known_command(f"/{command}@the_agent", "the_agent"))

    def test_is_known_command_accepts_command_with_trailing_args(self):
        self.assertTrue(is_known_command(f"/{COMMAND_CONNECT} ABC-123", "the_agent"))
        self.assertTrue(is_known_command(f"/{COMMAND_CONNECT}@the_agent ABC-123", "the_agent"))

    def test_is_known_command_rejects_known_command_with_wrong_tag(self):
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@otherbot", "the_agent"))

    def test_is_known_command_handles_missing_agent_handle(self):
        # untagged commands work even when the chat type has no resolvable agent handle
        self.assertTrue(is_known_command(f"/{COMMAND_HELP}", None))
        # tagged commands require a real handle to match against; None can never match
        self.assertFalse(is_known_command(f"/{COMMAND_HELP}@the_agent", None))

    def test_start_command_no_sponsorship(self):
        result = self.processor.execute(f"/{COMMAND_START}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_start_command_with_sponsorship(self):
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user(
            telegram_chat_id = "test_chat_id",
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
        )))
        sponsorship = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = uuid4(), receiver_id = self.di.invoker.id, accepted_at = None,
        ))

        result = self.processor.execute(f"/{COMMAND_START}")

        self.assertEqual(result.status, "success")
        self.assertIsNotNone(self.di.sponsorship_repo.get(sponsorship.sponsor_id, sponsorship.receiver_id).accepted_at)
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_settings_command(self):
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user(
            telegram_chat_id = "test_chat_id",
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
        )))
        sponsorship = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = uuid4(), receiver_id = self.di.invoker.id, accepted_at = None,
        ))
        result = self.processor.execute(f"/{COMMAND_SETTINGS}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )
        self.assertIsNone(self.di.sponsorship_repo.get(sponsorship.sponsor_id, sponsorship.receiver_id).accepted_at)

    def test_start_command_with_bot_tag(self):
        bot_tag = resolve_agent_user(self.di.invoker_chat_type).telegram_username
        result = self.processor.execute(f"/{COMMAND_START}@{bot_tag}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_settings_command_with_bot_tag(self):
        bot_tag = resolve_agent_user(self.di.invoker_chat_type).telegram_username
        result = self.processor.execute(f"/{COMMAND_SETTINGS}@{bot_tag}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_wrong_bot_tagged(self):
        result = self.processor.execute(f"/{COMMAND_START}@wrong_bot")
        self.assertEqual(result.status, "ignored")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_unknown_command(self):
        result = self.processor.execute("/unknown_command")
        self.assertEqual(result.status, "ignored")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_start_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_START} some extra arguments")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_settings_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_SETTINGS} some extra arguments")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_exception_in_settings_controller(self):
        self.di.invoker.telegram_user_id = None

        result = self.processor.execute(f"/{COMMAND_START}")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_exception_in_telegram_sdk(self):
        self.api.delivery_errors[self.di.invoker.telegram_chat_id] = ExternalServiceError("Telegram error", UNEXPECTED_ERROR)

        result = self.processor.execute(f"/{COMMAND_START}")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_help_command(self):
        result = self.processor.execute(f"/{COMMAND_HELP}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_help_command_with_bot_tag(self):
        bot_tag = resolve_agent_user(self.di.invoker_chat_type).telegram_username
        result = self.processor.execute(f"/{COMMAND_HELP}@{bot_tag}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_help_command_with_arguments_ignored(self):
        result = self.processor.execute(f"/{COMMAND_HELP} some extra arguments")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_exception_in_help_link_creation(self):
        self.di.invoker.telegram_user_id = None

        result = self.processor.execute(f"/{COMMAND_HELP}")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "Failed to process command.")
        self.assertEqual(result.error_code, UNEXPECTED_ERROR)
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_connect_command_no_key_provided(self):
        result = self.processor.execute(f"/{COMMAND_CONNECT}")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )

    def test_connect_command_successful(self):
        self.di.user_repo.save(stubs.domain.user(
            id = uuid4(),
            connect_key = "ABCD-EFGH-JKLM",
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "other-whatsapp-user",
        ))

        result = self.processor.execute(f"/{COMMAND_CONNECT} abcd-efgh-jklm")

        self.assertEqual(result.status, "success")
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("test_chat_id") if "text" in message], ["✅"])
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [],
        )

    def test_connect_command_invalid_key(self):
        result = self.processor.execute(f"/{COMMAND_CONNECT} INVALID-KEY")

        self.assertEqual(result.status, "success")
        self.assertEqual(
            [message["text"] for message in self.api.get_sent_messages("test_chat_id") if "text" in message],
            ["Invalid connect key. Please check the key and try again."],
        )
        self.assertEqual(
            [
                (message["link_url"], message["button_text"])
                for message in self.api.get_sent_messages("test_chat_id") if "link_url" in message
            ],
            [("https://example.com/settings?token=abc123", "⚙️")],
        )
