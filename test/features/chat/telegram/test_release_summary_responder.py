import base64
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import UUID

from langchain_core.messages import AIMessage

from api.model.release_output_payload import ReleaseOutputPayload
from db.crud.sponsorship import SponsorshipCRUD
from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import UserSave
from di.di import DI
from features.announcements.release_summary_service import ReleaseSummaryService
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_repo import ChatConfigRepository

# noinspection PyProtectedMember
from features.chat.telegram.release_summary_responder import (
    VersionChangeType,
    _strip_title_formatting,
    get_version_change_type,
    is_chat_subscribed,
    respond_with_summary,
)
from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.external_tools.tool_choice_resolver import ToolChoiceResolver
from features.integrations.integrations import resolve_agent_user
from features.integrations.platform_bot_sdk import PlatformBotSDK
from util.translations_cache import TranslationsCache


class ReleaseSummaryResponderTest(unittest.TestCase):

    agent_user: UserSave
    mock_di: DI
    payload: ReleaseOutputPayload

    def setUp(self):
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        # Create a DI mock and set required properties
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_crud = Mock(spec = UserCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.chat_config_repo = Mock(spec = ChatConfigRepository)
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_crud = Mock(spec = SponsorshipCRUD)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_sdk = Mock(spec = TelegramBotSDK)
        self.mock_di.telegram_bot_sdk.api = Mock(spec = TelegramBotAPI)
        # noinspection PyPropertyAccess
        self.mock_di.translations_cache = TranslationsCache()
        # noinspection PyPropertyAccess
        self.mock_di.tool_choice_resolver = Mock(spec = ToolChoiceResolver)
        # noinspection PyPropertyAccess
        self.mock_di.release_summary_service = Mock(spec = ReleaseSummaryService)
        release_output_json = {
            "latest_version": "1.0.0",
            "new_target_version": "1.0.1",
            "release_quality": "stable",
            "release_notes_b64": base64.b64encode(b"notes").decode(),
        }
        self.payload = ReleaseOutputPayload(
            release_output_b64 = base64.b64encode(json.dumps(release_output_json).encode()).decode(),
        )

        # Mock the user_dao.get() to return a proper UserDB for the agent's user
        mock_user_db = UserDB(
            id = self.agent_user.id,
            full_name = self.agent_user.full_name,
            telegram_username = self.agent_user.telegram_username,
            telegram_chat_id = self.agent_user.telegram_chat_id,
            telegram_user_id = self.agent_user.telegram_user_id,
            connect_key = "REL-SUM-KEY1",
            open_ai_key = self.agent_user.open_ai_key,
            anthropic_key = "test-anthropic-key",
            credit_balance = 0.0,
            perplexity_key = self.agent_user.perplexity_key,
            replicate_key = self.agent_user.replicate_key,
            rapid_api_key = self.agent_user.rapid_api_key,
            coinmarketcap_key = self.agent_user.coinmarketcap_key,
            group = self.agent_user.group,
            created_at = datetime.now().date(),
        )
        self.mock_di.user_crud.get.return_value = mock_user_db

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
        chat = self.__make_chat(ChatConfigDB.ReleaseNotifications.all)
        for change in VersionChangeType:
            self.assertTrue(is_chat_subscribed(chat, change))

    def test_is_chat_subscribed_none(self):
        chat = self.__make_chat(ChatConfigDB.ReleaseNotifications.none)
        for change in VersionChangeType:
            self.assertFalse(is_chat_subscribed(chat, change))

    def test_is_chat_subscribed_major(self):
        chat = self.__make_chat(ChatConfigDB.ReleaseNotifications.major)
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.major))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.minor))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.patch))

    def test_is_chat_subscribed_minor(self):
        chat = self.__make_chat(ChatConfigDB.ReleaseNotifications.minor)
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.major))
        self.assertTrue(is_chat_subscribed(chat, VersionChangeType.minor))
        self.assertFalse(is_chat_subscribed(chat, VersionChangeType.patch))

    @patch("features.chat.telegram.release_summary_responder.base64.b64decode")
    def test_decoding_failure(self, mock_b64decode):
        mock_b64decode.side_effect = Exception("decode error")
        payload = ReleaseOutputPayload(release_output_b64 = "invalid")
        result = respond_with_summary(payload, self.mock_di)
        self.assertIn("Failed to decode release notes", result["summary"])
        self.assertEqual(result["summaries_created"], 0)

    @patch("features.chat.telegram.release_summary_responder.config")
    def test_version_mismatch(self, mock_config):
        mock_config.version = "1.0.0"
        release_output_json = {
            "latest_version": "1.0.0",
            "new_target_version": "1.0.1",
            "release_quality": "stable",
            "release_notes_b64": base64.b64encode(b"notes").decode(),
        }
        payload = ReleaseOutputPayload(
            release_output_b64 = base64.b64encode(json.dumps(release_output_json).encode()).decode(),
        )
        result = respond_with_summary(payload, self.mock_di)
        self.assertIn("Skipping release processing", result["summary"])
        self.assertIn("1.0.0", result["summary"])
        self.assertIn("1.0.1", result["summary"])
        self.assertEqual(result["summaries_created"], 0)
        self.assertEqual(result["chats_notified"], 0)
        self.assertTrue(result["should_retry"])

    @patch("features.chat.telegram.release_summary_responder.config")
    def test_version_match(self, mock_config):
        mock_config.version = "1.0.1"
        mock_configured_tool = Mock()
        self.mock_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool
        mock_summary_service = Mock(spec = ReleaseSummaryService)
        mock_summary_service.execute.return_value = Mock(content = "Test summary")
        self.mock_di.release_summary_service.return_value = mock_summary_service
        self.mock_di.chat_config_repo.get_all.return_value = []
        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["summaries_created"], 1)
        self.assertNotIn("Skipping", result["summary"])
        self.assertFalse(result["should_retry"])

    @patch("features.chat.telegram.release_summary_responder.config")
    def test_successful_summary(self, mock_config):
        mock_config.version = "1.0.1"
        # Mock tool choice resolver and release summary service
        mock_configured_tool = Mock()
        self.mock_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        mock_summary_service = Mock(spec = ReleaseSummaryService)
        mock_summary_service.execute.return_value = Mock(content = "Test summary")
        self.mock_di.release_summary_service.return_value = mock_summary_service

        # Use the real translations cache - it will cache summaries as needed

        # Mock chat config
        self.mock_di.chat_config_repo.get_all.return_value = [self.__make_chat()]

        # Mock scoped DI and platform SDK for cloning
        mock_scoped_di = Mock()
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        mock_scoped_di.platform_bot_sdk = Mock(return_value = mock_platform_sdk)
        self.mock_di.clone = Mock(return_value = mock_scoped_di)

        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_notified"], 1)
        # noinspection PyUnresolvedReferences
        mock_platform_sdk.send_text_message.assert_called_once_with("1234", "Test summary")

    @patch("features.chat.telegram.release_summary_responder.config")
    def test_multiple_languages(self, mock_config):
        mock_config.version = "1.0.1"
        mock_summarizer = Mock(spec = ReleaseSummaryService)
        mock_summarizer.execute.return_value = AIMessage(content = "Summary")
        self.mock_di.release_summary_service.return_value = mock_summarizer
        self.mock_di.chat_config_repo.get_all.return_value = [
            self.__make_chat(chat_id = "123", lang_name = "English", lang_iso = "en"),
            self.__make_chat(chat_id = "456", lang_name = "Spanish", lang_iso = "es"),
        ]
        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_notified"], 2)
        self.assertEqual(result["summaries_created"], 2)

    def test_telegram_send_failure(self):
        # Mock tool choice resolver and release summary service
        mock_configured_tool = Mock()
        self.mock_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        mock_summary_service = Mock(spec = ReleaseSummaryService)
        mock_summary_service.execute.return_value = Mock(content = "Summary")
        self.mock_di.release_summary_service.return_value = mock_summary_service

        # Use the real translations cache

        # Mock chat config
        self.mock_di.chat_config_repo.get_all.return_value = [self.__make_chat()]

        # Mock scoped DI with platform SDK send failure
        mock_scoped_di = Mock()
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        mock_platform_sdk.send_text_message.side_effect = Exception("fail")
        mock_scoped_di.platform_bot_sdk = Mock(return_value = mock_platform_sdk)
        self.mock_di.clone = Mock(return_value = mock_scoped_di)

        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_notified"], 0)

    def test_no_eligible_chats(self):
        # Mock tool choice resolver and release summary service
        mock_configured_tool = Mock()
        self.mock_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        mock_summary_service = Mock(spec = ReleaseSummaryService)
        mock_summary_service.execute.return_value = Mock(content = "Summary")
        self.mock_di.release_summary_service.return_value = mock_summary_service

        # Use the real translations cache

        # Mock empty chat config list
        self.mock_di.chat_config_repo.get_all.return_value = []

        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_eligible"], 0)

    @patch("features.chat.telegram.release_summary_responder.config")
    def test_all_translations(self, mock_config):
        mock_config.version = "1.0.1"
        mock_sum = Mock(spec = ReleaseSummaryService)
        mock_sum.execute.return_value = Mock(content = "Gen summary")
        self.mock_di.release_summary_service.return_value = mock_sum
        self.mock_di.chat_config_repo.get_all.return_value = [
            self.__make_chat(chat_id = "123", lang_name = "English", lang_iso = "en"),
            self.__make_chat(chat_id = "456", lang_name = "Spanish", lang_iso = "es"),
            self.__make_chat(chat_id = "789", lang_name = "Greek", lang_iso = "gr"),
            self.__make_chat(chat_id = "sss", lang_name = "Spanish", lang_iso = "es"),
            self.__make_chat(chat_id = "eee", lang_name = "English", lang_iso = "en"),
        ]
        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_eligible"], 5)
        self.assertEqual(result["chats_notified"], 5)
        self.assertEqual(result["summaries_created"], 3)

    def test_summarization_failure(self):
        # Mock tool choice resolver and failing release summary service
        mock_configured_tool = Mock()
        self.mock_di.tool_choice_resolver.require_tool.return_value = mock_configured_tool

        mock_summary_service = Mock(spec = ReleaseSummaryService)
        mock_summary_service.execute.side_effect = Exception("boom")
        self.mock_di.release_summary_service.return_value = mock_summary_service

        # Mock chat config
        self.mock_di.chat_config_repo.get_all.return_value = [self.__make_chat()]

        result = respond_with_summary(self.payload, self.mock_di)
        self.assertEqual(result["chats_notified"], 0)
        self.assertIsNotNone(result["summary"])

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

    @staticmethod
    def __make_chat(
        notifications: ChatConfigDB.ReleaseNotifications = ChatConfigDB.ReleaseNotifications.all,
        media_mode: ChatConfigDB.MediaMode = ChatConfigDB.MediaMode.photo,
        chat_id: str = "1234",
        lang_name: str = "English",
        lang_iso: str = "en",
    ) -> ChatConfig:
        return ChatConfig(
            chat_id = UUID(int = 1),
            external_id = chat_id,
            language_name = lang_name,
            language_iso_code = lang_iso,
            title = "Chat Title",
            is_private = True,
            reply_chance_percent = 100,
            release_notifications = notifications,
            media_mode = media_mode,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
