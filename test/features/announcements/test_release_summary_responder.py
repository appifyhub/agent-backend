from typing import cast
from unittest import TestCase
from uuid import uuid4

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from util.di_utils import di_for_tests

from api.model.release_output_payload import ReleaseOutputPayload
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.announcements.release_summary_responder import (
    VersionChangeType,
    _strip_title_formatting,
    get_version_change_type,
    is_chat_subscribed,
    respond_with_summary,
)
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from util.config import config
from util.error_codes import UNEXPECTED_ERROR
from util.errors import ExternalServiceError


class ReleaseSummaryResponderTest(TestCase):

    di: DI
    payload: ReleaseOutputPayload
    model: FakeChatModel
    bot: FakeTelegramBotAPI

    def setUp(self):
        self.addCleanup(setattr, config, "version", config.version)
        config.version = "1.0.1"
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(tool))
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.payload = stubs.api.release_output_payload()

    def test_version_change_type_major(self):
        self.assertEqual(get_version_change_type("1.0.0", "2.0.0"), VersionChangeType.major)
        self.assertEqual(get_version_change_type("1", "2.0.0"), VersionChangeType.major)
        self.assertEqual(get_version_change_type("1.0.0", "2"), VersionChangeType.major)
        self.assertEqual(get_version_change_type("malformed", "1.0.0"), VersionChangeType.major)
        self.assertEqual(get_version_change_type("1.0.0", "malformed"), VersionChangeType.major)

    def test_version_change_type_minor(self):
        self.assertEqual(get_version_change_type("1.2.0", "1.3.0"), VersionChangeType.minor)
        self.assertEqual(get_version_change_type("1", "1.3.0"), VersionChangeType.minor)
        self.assertEqual(get_version_change_type("1.2.0", "1.3"), VersionChangeType.minor)

    def test_version_change_type_patch(self):
        self.assertEqual(get_version_change_type("1.2.3", "1.2.4"), VersionChangeType.patch)
        self.assertEqual(get_version_change_type("1.2.3", "1.2.3"), VersionChangeType.patch)
        self.assertEqual(get_version_change_type("1.2", "1.2.1"), VersionChangeType.patch)
        self.assertEqual(get_version_change_type("1", "1.0.1"), VersionChangeType.patch)

    def test_is_chat_subscribed_all(self):
        chat = stubs.domain.chat_config(release_notifications = ChatConfigDB.ReleaseNotifications.all)
        for change in VersionChangeType:
            self.assertTrue(is_chat_subscribed(chat, change))

    def test_is_chat_subscribed_none(self):
        chat = stubs.domain.chat_config(release_notifications = ChatConfigDB.ReleaseNotifications.none)
        for change in VersionChangeType:
            self.assertFalse(is_chat_subscribed(chat, change))

    def test_is_chat_subscribed_major(self):
        chat = stubs.domain.chat_config()
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.major))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.minor))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.patch))

    def test_is_chat_subscribed_minor(self):
        chat = stubs.domain.chat_config(release_notifications = ChatConfigDB.ReleaseNotifications.minor)
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.major))
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.minor))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.patch))

    def test_decoding_failure(self):
        payload = stubs.api.release_output_payload(release_output_b64 = "invalid")

        result = respond_with_summary(payload, self.di)

        self.assertIn("Failed to decode release notes", result["summary"])
        self.assertEqual(result["summaries_created"], 0)
        self.assertEqual(self.model.prompts, [])

    def test_version_mismatch(self):
        config.version = "1.0.0"

        result = respond_with_summary(self.payload, self.di)

        self.assertIn("Skipping release processing", result["summary"])
        self.assertIn("1.0.0", result["summary"])
        self.assertIn("1.0.1", result["summary"])
        self.assertEqual(result["summaries_created"], 0)
        self.assertEqual(result["chats_notified"], 0)
        self.assertTrue(result["should_retry"])
        self.assertEqual(self.model.prompts, [])

    def test_version_match(self):
        self.model.responses.append(stubs.external.ai_message(content = "Test summary"))

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["summaries_created"], 1)
        self.assertEqual(result["summary"], "Test summary")
        self.assertFalse(result["should_retry"])
        self.assertEqual(self.model.prompts[0][-1].content, "notes")

    def test_successful_summary(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
        ))
        self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "unsubscribed"))
        self.model.responses.append(stubs.external.ai_message(content = "## Test summary"))

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["summary"], "Test summary")
        self.assertEqual(result["chats_eligible"], 2)
        self.assertEqual(result["chats_subscribed"], 1)
        self.assertEqual(result["chats_unsubscribed"], 1)
        self.assertEqual(result["chats_notified"], 1)
        self.assertEqual(result["summaries_created"], 1)
        self.assertEqual([message["text"] for message in self.bot.get_sent_messages(chat.external_id)], ["Test summary"])
        self.assertEqual(self.bot.get_sent_messages("unsubscribed"), [])

    def test_multiple_languages(self):
        self.di.chat_config_repo.save(stubs.domain.chat_config(
            external_id = "123", release_notifications = ChatConfigDB.ReleaseNotifications.all,
        ))
        self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(), external_id = "456", language_name = "Spanish", language_iso_code = "es",
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
        ))
        self.model.responses.extend([
            stubs.external.ai_message(content = "English summary"),
            stubs.external.ai_message(content = "Spanish summary"),
        ])

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["chats_notified"], 2)
        self.assertEqual(result["summaries_created"], 2)
        self.assertEqual([message["text"] for message in self.bot.get_sent_messages("123")], ["English summary"])
        self.assertEqual([message["text"] for message in self.bot.get_sent_messages("456")], ["Spanish summary"])

    def test_telegram_send_failure(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
        ))
        self.bot.delivery_errors[chat.external_id] = ExternalServiceError("Delivery failed", UNEXPECTED_ERROR)
        self.model.responses.append(stubs.external.ai_message(content = "Summary"))

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["chats_subscribed"], 1)
        self.assertEqual(result["summaries_created"], 1)
        self.assertEqual(result["chats_notified"], 0)
        self.assertFalse(result["should_retry"])
        self.assertEqual(self.bot.get_sent_messages(chat.external_id), [])

    def test_no_eligible_chats(self):
        self.model.responses.append(stubs.external.ai_message(content = "Summary"))

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["chats_eligible"], 0)
        self.assertEqual(result["chats_notified"], 0)
        self.assertEqual(result["summaries_created"], 1)
        self.assertEqual(result["summary"], "Summary")
        self.assertFalse(result["should_retry"])

    def test_all_translations(self):
        for external_id, language_name, language_iso_code in (
            ("123", "English", "en"), ("456", "Spanish", "es"), ("789", "Greek", "gr"),
            ("sss", "Spanish", "es"), ("eee", "English", "en"),
        ):
            self.di.chat_config_repo.save(stubs.domain.chat_config(
                chat_id = uuid4(), external_id = external_id,
                language_name = language_name, language_iso_code = language_iso_code,
                release_notifications = ChatConfigDB.ReleaseNotifications.all,
            ))
        self.model.responses.extend([
            stubs.external.ai_message(content = "English summary"),
            stubs.external.ai_message(content = "Translated summary"),
            stubs.external.ai_message(content = "Translated summary"),
        ])

        result = respond_with_summary(self.payload, self.di)

        self.assertEqual(result["chats_eligible"], 5)
        self.assertEqual(result["chats_notified"], 5)
        self.assertEqual(result["summaries_created"], 3)
        self.assertEqual(len(self.model.prompts), 3)
        for external_id in ("123", "eee"):
            self.assertEqual([message["text"] for message in self.bot.get_sent_messages(external_id)], ["English summary"])
        for external_id in ("456", "789", "sss"):
            self.assertEqual([message["text"] for message in self.bot.get_sent_messages(external_id)], ["Translated summary"])

    def test_summarization_failure(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
        ))
        self.model.responses.append(ExternalServiceError("Generation failed", UNEXPECTED_ERROR))

        result = respond_with_summary(self.payload, self.di)

        self.assertIn("Release summary failed for default language", result["summary"])
        self.assertIn("Generation failed", result["summary"])
        self.assertEqual(result["summaries_created"], 0)
        self.assertEqual(result["chats_notified"], 0)
        self.assertFalse(result["should_retry"])
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.bot.get_sent_messages(chat.external_id), [])

    def test_strip_title_formatting(self):
        self.assertEqual(_strip_title_formatting("# Title\nContent"), "Title\nContent")
        self.assertEqual(_strip_title_formatting("##  Title\nContent"), "Title\nContent")
        self.assertEqual(_strip_title_formatting("###Title\nContent"), "Title\nContent")
        self.assertEqual(_strip_title_formatting("#    Title"), "Title")
        self.assertEqual(_strip_title_formatting("No title here"), "No title here")
        self.assertEqual(_strip_title_formatting("#######   Title"), "Title")
        self.assertEqual(_strip_title_formatting("#Title"), "Title")
        self.assertEqual(_strip_title_formatting("##\tTitle"), "Title")
        self.assertEqual(_strip_title_formatting("###   "), "")
