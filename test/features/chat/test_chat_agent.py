from dataclasses import replace
from datetime import datetime, timedelta
from json import loads
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_url_shortener import FakeUrlShortener
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from langchain_core.messages import HumanMessage, ToolMessage
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.membership.chat_membership_service import ChatMembershipService
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool_library import GPT_5_6_SOL
from features.integrations.integrations import resolve_agent_user
from features.users.user_repo import UserRepository
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS
from util.errors import AuthorizationError, ValidationError


class ChatAgentTest(TestCase):

    di: DI
    agent: ChatAgent
    tool: ConfiguredTool | None
    cutoff_sent_at: datetime
    members: ChatMembershipService
    messages: ChatMessageRepository
    users: UserRepository
    model: FakeChatModel
    api: FakeTelegramBotAPI

    def setUp(self):
        self.tool = domain.configured_tool(definition = GPT_5_6_SOL)
        self.di = self.enterContext(di_for_tests())
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool, max_tokens = 500))
        shortener = cast(FakeUrlShortener, self.di.url_shortener("https://example.com/settings"))
        shortener.short_url = "https://example.com/settings"
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.cutoff_sent_at = datetime(2026, 1, 15, 12)
        self.messages = self.di.chat_message_repo
        self.users = self.di.user_repo
        self.members = self.di.chat_membership_service
        user = domain.user(telegram_chat_id = "test_chat_id", is_invited_to_start = False)
        chat = domain.chat_config(is_private = False, reply_chance_percent = 100)
        self.di.inject_invoker(user)
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(chat))
        self.di.chat_config_repo.save(domain.chat_config(chat_id = uuid4(), external_id = "test_chat_id"))
        self.users.save(user)
        self.members.save(domain.chat_membership(user_id = user.id, chat_id = chat.chat_id, max_output_tokens = 500))
        self.messages.save(domain.chat_message(
            message_id = "msg_123",
            sent_at = self.cutoff_sent_at,
            text = "Test message",
            ingestion_order = 7,
        ))
        self.agent = self.__create_agent()

    def __create_agent(self, trigger_text: str = "Test message", explicitly_addressed: bool = False) -> ChatAgent:
        return self.di.chat_agent(
            trigger_message_text = trigger_text,
            trigger_message_id = "msg_123",
            configured_tool = self.tool,
            cutoff_sent_at = self.cutoff_sent_at,
            cutoff_ingestion_order = 7,
            explicitly_addressed = explicitly_addressed,
        )

    def test_init_rejects_invoker_without_membership(self):
        self.di.inject_invoker(domain.user(id = UUID(int = 99)))

        with self.assertRaises(AuthorizationError):
            self.__create_agent()

    def test_process_commands_no_api_key(self):
        self.tool = None
        agent = self.__create_agent()

        result = agent.process_commands()

        self.assertFalse(result.is_handled)
        self.assertIsNone(result.reply)
        self.assertEqual(self.model.prompts, [])

    def test_process_commands_failed(self):
        result = self.__create_agent(trigger_text = "/start@bot@extra").process_commands()

        self.assertTrue(result.is_handled)
        self.assertEqual(result.reply.content, "👎")
        sent_messages = self.api.get_sent_messages("test_chat_id")
        self.assertEqual(len(sent_messages), 1)
        self.assertIn("Failed to process command.", sent_messages[0]["text"])

    def test_process_commands_success(self):
        result = self.__create_agent(trigger_text = "/help").process_commands()

        self.assertTrue(result.is_handled)
        self.assertIsNone(result.reply)
        self.assertEqual(self.model.prompts, [])

    def test_should_reply_private_chat(self):
        self.di.invoker_chat.is_private = True
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertTrue(self.agent.should_reply())

    def test_should_reply_explicitly_addressed(self):
        self.di.invoker_chat.reply_chance_percent = 0
        agent = self.__create_agent(explicitly_addressed = True)

        self.assertTrue(agent.should_reply())

    def test_should_not_reply_when_bot_mention_is_only_quoted(self):
        self.di.invoker_chat.reply_chance_percent = 0
        username = resolve_agent_user(ChatConfigDB.ChatType.telegram).telegram_username
        for quote_prefix in (">>", ">>>>"):
            with self.subTest(quote_prefix = quote_prefix):
                agent = self.__create_agent(trigger_text = f"{quote_prefix} Hello @{username}\n\nI agree")

                self.assertFalse(agent.should_reply())

    def test_should_reply_with_aggregated_addressing_after_quote(self):
        self.di.invoker_chat.reply_chance_percent = 0
        agent = self.__create_agent(trigger_text = ">> Quoted message\n\nHello", explicitly_addressed = True)

        self.assertTrue(agent.should_reply())

    def test_should_reply_random_chance(self):
        self.di.invoker_chat.reply_chance_percent = 50
        # random sampling is a system dependency, not an application decision
        with patch("random.randint", return_value = 25):
            self.assertTrue(self.agent.should_reply())
        with patch("random.randint", return_value = 75):
            self.assertFalse(self.agent.should_reply())

    def test_is_dispatchable_rejects_empty_message(self):
        agent = self.__create_agent(trigger_text = " ")

        self.assertIsNone(agent.execute())
        self.assertEqual(self.model.prompts, [])

    def test_should_not_reply_zero_chance(self):
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertFalse(self.agent.should_reply())

    def test_should_reply_100_chance(self):
        self.assertTrue(self.agent.should_reply())

    def test_should_reply_group_chat(self):
        self.di.invoker_chat.title = "Group Chat"

        self.assertTrue(self.agent.should_reply())

    def test_is_dispatchable_rejects_self_authored(self):
        self.di.invoker.telegram_username = resolve_agent_user(ChatConfigDB.ChatType.telegram).telegram_username

        self.assertIsNone(self.agent.execute())
        self.assertEqual(self.model.prompts, [])

    def test_is_dispatchable_accepts_other_user(self):
        self.di.invoker.telegram_username = "other_user"
        self.model.responses.append(external.ai_message(content = "Reply"))

        self.assertEqual(self.agent.execute().content, "Reply")

    def test_execute_no_reply_needed(self):
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertIsNone(self.agent.execute())
        self.assertEqual(self.model.prompts, [])

    def test_execute_no_api_key(self):
        self.tool = None
        agent = self.__create_agent()

        result = agent.execute()

        self.assertEqual(result.content, "👎")
        self.assertIn("Not configured", self.api.get_sent_messages("test_chat_id")[0]["text"])
        self.assertEqual(self.model.prompts, [])

    def test_execute_blocks_unfunded_whatsapp_before_byok_model(self):
        user = self.users.save(replace(
            self.di.invoker,
            credit_balance = 0.0,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(replace(
            self.di.require_invoker_chat(),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = user.whatsapp_user_id,
        ))
        self.di.inject_invoker(user)
        self.di.inject_invoker_chat(chat)
        self.tool = replace(self.tool, uses_credits = False, payer_id = user.id)
        agent = self.__create_agent()
        whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)

        with self.assertRaises(ValidationError) as context:
            agent.execute()

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(whatsapp.get_sent_messages(str(chat.external_id)), [])

    def test_execute_llm_response(self):
        self.model.responses.append(external.ai_message(content = "LLM response"))

        result = self.agent.execute()

        self.assertEqual(result.content, "LLM response")

    def test_execute_removes_attachment_placeholder_from_llm_response(self):
        self.model.responses.append(external.ai_message(content = "Here you go\n\n📎 [ a1 (image/png) ]\n\nDone"))

        self.assertEqual(self.agent.execute().content, "Here you go\n\nDone")

    def test_execute_removes_attachment_placeholder_only_llm_response(self):
        self.model.responses.append(external.ai_message(content = "📎 [ a1 (image/png) ]"))

        self.assertEqual(self.agent.execute().content, "")

    def test_execute_removes_attachment_placeholder_from_llm_content_blocks(self):
        self.model.responses.append(external.ai_message(content = [
            {"type": "text", "text": "Here\n📎 [ a1 (image/png) ]"},
            "📎 [ a2 ]",
            {"type": "thinking", "thinking": "internal"},
        ]))

        result = self.agent.execute()

        self.assertEqual(result.content, [
            {"type": "text", "text": "Here"},
            {"type": "thinking", "thinking": "internal"},
        ])

    def test_execute_tool_call(self):
        self.model.responses.extend([
            external.ai_message(content = "", tool_calls = [{"id": "1", "name": "get_version", "args": {}}]),
            external.ai_message(content = "Final response"),
        ])

        result = self.agent.execute()

        self.assertEqual(result.content, "Final response")
        tool_messages = [message for message in self.model.prompts[1] if isinstance(message, ToolMessage)]
        self.assertEqual([message.tool_call_id for message in tool_messages], ["1"])
        self.assertEqual(loads(tool_messages[0].content)["service_version"], f"v{config.version}")

    def test_execute_exception(self):
        self.model.responses.append(OSError("Test error"))

        result = self.agent.execute()

        self.assertEqual(result.content, "👎")
        sent_messages = self.api.get_sent_messages("test_chat_id")
        self.assertEqual(len(sent_messages), 1)
        self.assertIn("Test error", sent_messages[0]["text"])
        self.assertIn("Use /settings", sent_messages[0]["text"])

    def test_execute_max_iterations_exceeded(self):
        membership = self.members.get(self.di.invoker.id, self.di.invoker_chat.chat_id)
        self.members.save(replace(membership, max_iterations = 2))
        agent = self.__create_agent()
        self.model.responses.extend([
            external.ai_message(content = "", tool_calls = [{"id": "1", "name": "get_version", "args": {}}]),
            external.ai_message(content = "", tool_calls = [{"id": "2", "name": "get_version", "args": {}}]),
        ])

        result = agent.execute()

        self.assertEqual(result.content, "👎")
        self.assertIn("Reached max iterations (2)", self.api.get_sent_messages("test_chat_id")[0]["text"])
        self.assertEqual(len(self.model.prompts), 2)

    def test_execute_waitlist_guard_blocks_unknown_commands(self):
        self.di.invoker.is_on_waitlist = True

        result = self.agent.execute()

        self.assertEqual(result.content, "👎")
        self.assertIn("waitlist", self.api.get_sent_messages("test_chat_id")[0]["text"].lower())
        self.assertEqual(self.model.prompts, [])

    def test_execute_policy_guard_blocks_active_user_without_policy(self):
        self.di.invoker.are_policies_accepted = False

        result = self.agent.execute()

        self.assertEqual(result.content, "👎")
        self.assertIn("policies", self.api.get_sent_messages("test_chat_id")[0]["text"].lower())
        self.assertEqual(self.model.prompts, [])

    def test_init_bounds_history_to_claimed_cutoff(self):
        self.messages.save(domain.chat_message(
            message_id = "earlier",
            text = "Earlier",
            sent_at = self.cutoff_sent_at - timedelta(seconds = 1),
            ingestion_order = 6,
        ))
        self.messages.save(
            domain.chat_message(message_id = "later", text = "Later", sent_at = self.cutoff_sent_at, ingestion_order = 8),
        )
        membership = self.members.get(self.di.invoker.id, self.di.invoker_chat.chat_id)
        self.members.save(replace(membership, max_chat_history_depth = 1))
        agent = self.__create_agent(explicitly_addressed = True)
        self.model.responses.append(external.ai_message(content = "Reply"))

        agent.execute()

        history = [message.content for message in self.model.prompts[0] if isinstance(message, HumanMessage)]
        self.assertEqual(len(history), 1)
        self.assertIn("Test message", history[0])
        self.assertNotIn("Earlier", history[0])
        self.assertNotIn("Later", history[0])

    def test_should_reply_to_explicitly_addressed_group_burst(self):
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertTrue(self.__create_agent(explicitly_addressed = True).should_reply())

    def test_should_not_reply_to_unaddressed_zero_chance_group_burst(self):
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertFalse(self.__create_agent().should_reply())

    def test_should_reply_to_private_burst_without_explicit_address(self):
        self.di.invoker_chat.is_private = True
        self.di.invoker_chat.reply_chance_percent = 0

        self.assertTrue(self.__create_agent().should_reply())

    def test_error_routes_to_private_chat_as_single_message(self):
        self.di.invoker.is_on_waitlist = True

        result = self.agent.execute()

        self.assertEqual(result.content, "👎")
        sent_messages = self.api.get_sent_messages("test_chat_id")
        self.assertEqual(len(sent_messages), 1)
        sent_text = sent_messages[0]["text"]
        self.assertIn("🔒", sent_text)
        self.assertIn("The waitlist is not open yet", sent_text)
        self.assertIn("Use /settings", sent_text)

    def test_error_falls_back_to_inline_when_no_private_chat(self):
        self.di.invoker.telegram_chat_id = None
        self.di.invoker.is_on_waitlist = True

        result = self.agent.execute()

        self.assertIn("The waitlist is not open yet", result.content)
        self.assertIn("Use /settings", result.content)
        self.assertEqual(self.api.get_sent_messages("test_chat_id"), [])

    def test_error_routing_swallows_private_chat_delivery_failure(self):
        self.api.delivery_errors["test_chat_id"] = OSError("Network error")
        self.di.invoker.is_on_waitlist = True

        result = self.agent.execute()

        self.assertEqual(result.content, "👎")
        self.assertEqual(self.api.get_sent_messages("test_chat_id"), [])
