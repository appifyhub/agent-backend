from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfigDB
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool_library import GPT_5_6_SOL
from features.integrations.integrations import resolve_agent_user, resolve_external_id
from features.users.user_repo import UserRepository
from util.error_codes import UNEXPECTED_ERROR
from util.errors import AuthorizationError, ExternalServiceError, NotFoundError


class DevAnnouncementsServiceTest(TestCase):

    di: DI
    tool: ConfiguredTool
    chats: ChatConfigRepository
    users: UserRepository
    model: FakeChatModel
    api: FakeTelegramBotAPI

    def setUp(self):
        self.tool = domain.configured_tool(definition = GPT_5_6_SOL)
        self.di = self.enterContext(di_for_tests())
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool, max_tokens = 500))
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.chats = self.di.chat_config_repo
        self.users = self.di.user_repo
        self.di.inject_invoker(self.users.save(domain.user(
            telegram_user_id = 100,
            telegram_chat_id = "100",
            group = UserDB.Group.developer,
            whatsapp_user_id = "whatsapp-developer",
            whatsapp_phone_number = "+15559876543",
            connect_key = "DEVR-USER-0001",
        )))
        self.di.inject_invoker_chat(domain.chat_config())

    def test_init_success(self):
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        self.assertEqual(service.execute(), {"chats_selected": 0, "chats_notified": 0, "summaries_created": 0})

    def test_init_user_not_found(self):
        with self.assertRaises(NotFoundError):
            self.di.dev_announcements_service("Test announcement", "missing", self.tool)

    def test_init_user_not_developer(self):
        self.di.inject_invoker(replace(self.di.invoker, group = UserDB.Group.standard))

        with self.assertRaises(AuthorizationError):
            self.di.dev_announcements_service("Test announcement", None, self.tool)

    def test_execute_success(self):
        english = domain.chat_config(external_id = "1")
        spanish = domain.chat_config(chat_id = uuid4(), external_id = "2", language_iso_code = "es", language_name = "Spanish")
        self.chats.save(english)
        self.chats.save(spanish)
        self.chats.save(domain.chat_config(chat_id = uuid4(), external_id = "3"))
        self.model.responses.extend([
            external.ai_message(content = "English announcement"),
            external.ai_message(content = "Spanish announcement"),
        ])
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 3, "chats_notified": 3, "summaries_created": 2})
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("1")], ["English announcement"])
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("2")], ["Spanish announcement"])
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("3")], ["English announcement"])
        self.assertEqual(len(self.model.prompts), 2)

    def test_execute_translation_failure(self):
        self.chats.save(domain.chat_config(external_id = "1"))
        self.model.responses.append(ExternalServiceError("Translation failed", UNEXPECTED_ERROR))
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 1, "chats_notified": 0, "summaries_created": 0})
        self.assertEqual(self.api.get_sent_messages("1"), [])

    def test_execute_notification_failure(self):
        chat = domain.chat_config(external_id = "1")
        self.chats.save(chat)
        self.model.responses.append(external.ai_message(content = "Translated announcement"))
        self.api.delivery_errors["1"] = ExternalServiceError("Notification failed", UNEXPECTED_ERROR)
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 1, "chats_notified": 0, "summaries_created": 1})
        self.assertEqual(self.api.get_sent_messages("1"), [])

    def test_execute_no_chats(self):
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 0, "chats_notified": 0, "summaries_created": 0})
        self.assertEqual(self.model.prompts, [])

    def test_targeted_announcement_success(self):
        self.model.responses.append(external.ai_message(content = [
            {"type": "thinking", "thinking": "Hidden reasoning"},
            {"type": "text", "text": "Refined announcement"},
        ]))
        self.users.save(domain.user(id = uuid4(), telegram_username = "target_user", telegram_user_id = 12345))
        self.chats.save(domain.chat_config(external_id = "12345"))
        self.chats.save(domain.chat_config(chat_id = uuid4(), external_id = "67890"))
        service = self.di.dev_announcements_service("Test announcement", "target_user", self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 1, "chats_notified": 1, "summaries_created": 1})
        self.assertEqual([message["text"] for message in self.api.get_sent_messages("12345")], ["Refined announcement"])
        self.assertEqual(self.api.get_sent_messages("67890"), [])
        self.assertEqual(self.model.prompts[0][-1].content, "Test announcement")

    def test_targeted_announcement_invalid_username(self):
        with self.assertRaises(NotFoundError) as context:
            self.di.dev_announcements_service("Test announcement", "nonexistent_user", self.tool)

        self.assertIn("Target user 'nonexistent_user' not found", str(context.exception))

    def test_targeted_announcement_no_external_id(self):
        self.users.save(domain.user(telegram_username = "target_user", telegram_user_id = None))

        with self.assertRaises(AuthorizationError) as context:
            self.di.dev_announcements_service("Test announcement", "target_user", self.tool)

        self.assertIn("has no external ID", str(context.exception))

    def test_targeted_announcement_chat_not_found(self):
        self.users.save(domain.user(telegram_username = "target_user", telegram_user_id = 12345))

        with self.assertRaises(NotFoundError) as context:
            self.di.dev_announcements_service("Test announcement", "target_user", self.tool)

        self.assertIn("Target chat '12345' not found", str(context.exception))

    def test_execute_excludes_invoker_and_agent_chats(self):
        chat_type = self.di.require_invoker_chat_type()
        agent_id = resolve_external_id(resolve_agent_user(chat_type), chat_type)
        self.chats.save(domain.chat_config(chat_id = uuid4(), external_id = "100"))
        self.chats.save(domain.chat_config(chat_id = uuid4(), external_id = agent_id))
        service = self.di.dev_announcements_service("Test announcement", None, self.tool)

        result = service.execute()

        self.assertEqual(result, {"chats_selected": 0, "chats_notified": 0, "summaries_created": 0})
        self.assertEqual(self.model.prompts, [])

    def test_unfunded_whatsapp_target_is_not_generated_or_notified(self):
        developer = self.users.save(replace(
            self.di.invoker,
            credit_balance = 0.0,
            whatsapp_user_id = "15551234566",
        ))
        target = self.users.save(domain.user(
            id = uuid4(),
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "15551234567",
            whatsapp_phone_number = "+15551234568",
            connect_key = "ANNC-TRGT-0001",
        ))
        chat = self.chats.save(domain.chat_config(
            chat_id = uuid4(),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = target.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(domain.chat_membership(
            chat_id = chat.chat_id,
            user_id = target.id,
        ))
        self.di.inject_invoker(developer)
        self.di.inject_invoker_chat(self.chats.save(domain.chat_config(
            chat_id = uuid4(),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = developer.whatsapp_user_id,
        )))
        service = self.di.dev_announcements_service(
            "Service update",
            "15551234567",
            self.tool,
        )

        with patch("features.chat.dev_announcements_service.log.w") as warning_log:
            result = service.execute()

        self.assertEqual(result, {
            "chats_selected": 1, "chats_notified": 0, "summaries_created": 0,
        })
        self.assertEqual(self.model.prompts, [])
        warning_log.assert_called_once_with(f"Skipping announcement for chat #{chat.chat_id} due to insufficient delivery credits")  # ruff: ignore[line-too-long]
