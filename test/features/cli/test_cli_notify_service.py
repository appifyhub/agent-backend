from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest import TestCase
from uuid import UUID, uuid4

import stubs
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from requests import Timeout
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.usage.usage_record import UsageRecord
from features.chat.config.chat_config import ChatConfig
from features.cli.cli_notify_service import CliNotifyService
from features.external_tools.external_tool import ToolType
from features.integrations.integrations import measure_text_message_length, resolve_agent_user
from features.users.user import User
from util.config import config
from util.error_codes import (
    CHAT_NOT_FOUND,
    INSUFFICIENT_CREDITS,
    INVALID_NOTIFICATION_MESSAGE,
    INVALID_PLATFORM,
    MALFORMED_CHAT_ID,
    NO_PRIVATE_CHAT,
    NOT_CHAT_ADMIN,
    NOT_CHAT_MEMBER,
    NOTIFICATION_DELIVERY_FAILED,
    WAITLIST_ACCOUNT_NOT_ACTIVE,
    WAITLIST_INVITED_POLICIES_REQUIRED,
)
from util.errors import ServiceError

HOSTNAME = "laptop"
MAX_NOTIFICATION_LENGTH = 4096
USERNAME_PREFIX = "🖥️  [mark_johnson@laptop] "


class CliNotifyServiceTest(TestCase):

    di: DI
    service: CliNotifyService
    owner: User
    telegram: FakeTelegramBotAPI
    whatsapp: FakeWhatsAppBotAPI
    pricing_path: Path

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.owner = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.owner)
        self.service = self.di.cli_notify_service
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.pricing_path = Path(self.enterContext(TemporaryDirectory())) / "platform-pricing.yaml"
        self.__set_pricing(telegram = "0", whatsapp = "0.7")
        self.addCleanup(
            setattr,
            config,
            "integration_delivery_pricing_config_path",
            config.integration_delivery_pricing_config_path,
        )
        config.integration_delivery_pricing_config_path = str(self.pricing_path)

    def __set_pricing(self, telegram: str, whatsapp: str) -> None:
        self.pricing_path.write_text(f"""\
platforms:
  telegram:
    markets:
      global: {{default: true, categories: {{service: "{telegram}"}}}}
  whatsapp:
    markets:
      global: {{default: true, categories: {{service: "{whatsapp}"}}}}
""")

    def __save_telegram_private(self, hours_since_owner_message: float | None = None) -> ChatConfig:
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = str(self.owner.telegram_user_id)))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = self.owner.id, chat_id = chat.chat_id))
        self.__save_owner_message(chat, hours_since_owner_message)
        return chat

    def __save_whatsapp_private(self, hours_since_owner_message: float | None = None) -> ChatConfig:
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("33333333-3333-4333-8333-c33333333333"),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = self.owner.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = self.owner.id, chat_id = chat.chat_id))
        self.__save_owner_message(chat, hours_since_owner_message)
        return chat

    def __save_owner_message(self, chat: ChatConfig, hours_ago: float | None) -> None:
        if hours_ago is None:
            return
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = self.owner.id,
            sent_at = datetime.now() - timedelta(hours = hours_ago),
            ingestion_order = None,
        ))

    def __save_group(self, member: Any = None, external_id: str = "group-1") -> ChatConfig:
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(), external_id = external_id, title = "Team", is_private = False,
        ))
        if member is not None:
            self.telegram.members[(external_id, str(self.owner.telegram_user_id))] = member
        return chat

    def __service_for(self, invoker: User | None) -> CliNotifyService:
        if invoker is None:
            return self.service
        invoker_di = self.di.clone()
        invoker_di.inject_invoker(invoker)
        return invoker_di.cli_notify_service

    def __notify_user(
        self, message: str = "Build finished", platform: str | None = None, user: User | None = None,
    ) -> CliNotifyService.Delivery:
        return self.__service_for(user).notify_invoker(HOSTNAME, message, platform)

    def __notify_chat(
        self, chat_id: str | UUID, message: str = "Build finished", user: User | None = None,
    ) -> CliNotifyService.Delivery:
        return self.__service_for(user).notify_chat(HOSTNAME, chat_id, message)

    def __sent_texts(self, chat: ChatConfig) -> list[str]:
        sent = self.whatsapp if chat.chat_type == ChatConfigDB.ChatType.whatsapp else self.telegram
        return [message["text"] for message in sent.get_sent_messages(str(chat.external_id))]

    def __delivery_records(self) -> list[UsageRecord]:
        return [
            record for record in self.di.usage_record_repo.get_by_user(self.owner.id)
            if record.tool_purpose == ToolType.message_delivery
        ]

    def __balance(self) -> float:
        return self.di.authorization_service.validate_user(self.owner.id).credit_balance

    def __assert_rejected(self, error_code: int, http_status: int, call, *chats: ChatConfig) -> ServiceError:
        with self.assertRaises(ServiceError) as context:
            call()
        self.assertEqual(context.exception.error_code, error_code)
        self.assertEqual(context.exception.http_status, http_status)
        for chat in chats:
            self.assertEqual(self.__sent_texts(chat), [])
        self.assertEqual(self.__balance(), self.owner.credit_balance)
        return context.exception

    def test_not_onboarded_owner_is_rejected_before_anything_else(self):
        chat = self.__save_telegram_private()
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        cases = [
            ({"is_on_waitlist": True, "is_invited_to_start": False, "are_policies_accepted": False}, WAITLIST_ACCOUNT_NOT_ACTIVE),
            ({"is_on_waitlist": True, "is_invited_to_start": True, "are_policies_accepted": False}, WAITLIST_INVITED_POLICIES_REQUIRED),  # ruff: ignore[line-too-long]
            ({"is_on_waitlist": False, "is_invited_to_start": False, "are_policies_accepted": False}, WAITLIST_INVITED_POLICIES_REQUIRED),  # ruff: ignore[line-too-long]
            ({"is_on_waitlist": True, "is_invited_to_start": True, "are_policies_accepted": True}, WAITLIST_ACCOUNT_NOT_ACTIVE),
        ]
        for state, error_code in cases:
            user = replace(self.owner, **state)
            calls = {
                "user": lambda user = user: self.__notify_user("   ", platform = "unsupported", user = user),
                "chat": lambda user = user: self.__notify_chat(group.chat_id.hex, "   ", user = user),
            }
            for route, call in calls.items():
                with self.subTest(state = state, route = route):
                    self.__assert_rejected(error_code, 403, call, chat, group)

    def test_message_is_trimmed_and_interior_line_breaks_are_kept(self):
        chat = self.__save_telegram_private()

        self.__notify_user("  Build\n\nfinished  ")

        self.assertEqual(self.__sent_texts(chat), [USERNAME_PREFIX + "Build\n\nfinished"])

    def test_blank_and_oversized_messages_are_rejected_at_the_boundary(self):
        chat = self.__save_telegram_private()
        for message in ("", "   \n\t", "a" * (MAX_NOTIFICATION_LENGTH + 1)):
            with self.subTest(length = len(message)):
                self.__assert_rejected(INVALID_NOTIFICATION_MESSAGE, 422, lambda message = message: self.__notify_user(message), chat)  # ruff: ignore[line-too-long]

        self.__notify_user("a" * MAX_NOTIFICATION_LENGTH)

        self.assertEqual(len(self.__sent_texts(chat)), 1)

    def test_explicit_platform_targets_the_private_chat_on_that_platform(self):
        telegram_chat = self.__save_telegram_private()
        whatsapp_chat = self.__save_whatsapp_private(hours_since_owner_message = 48)

        telegram_delivery = self.__notify_user(platform = "telegram")
        whatsapp_delivery = self.__notify_user(platform = "whatsapp")

        self.assertEqual(telegram_delivery.chat, telegram_chat)
        self.assertEqual(whatsapp_delivery.chat, whatsapp_chat)
        self.assertEqual(self.__sent_texts(whatsapp_chat), ["🖥️  [+15551234567@laptop] Build finished"])

    def test_explicit_platform_without_a_private_chat_is_rejected(self):
        self.__save_telegram_private()
        group = self.__save_group(external_id = "group-on-whatsapp-owner-id")
        self.di.chat_config_repo.save(replace(
            stubs.domain.chat_config(), chat_id = uuid4(), chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = "someone-else", is_private = False,
        ))

        self.__assert_rejected(NO_PRIVATE_CHAT, 403, lambda: self.__notify_user(platform = "whatsapp"), group)

    def test_unsupported_platforms_are_rejected(self):
        chat = self.__save_telegram_private()
        for platform in ("github", "background", "signal", "TELEGRAM", ""):
            with self.subTest(platform = platform):
                self.__assert_rejected(INVALID_PLATFORM, 422, lambda platform = platform: self.__notify_user(platform = platform), chat)  # ruff: ignore[line-too-long]

    def test_default_target_follows_the_best_chat_rule(self):
        self.__assert_rejected(NO_PRIVATE_CHAT, 403, lambda: self.__notify_user())

        telegram_chat = self.__save_telegram_private(hours_since_owner_message = 10)
        self.assertEqual(self.__notify_user().chat, telegram_chat)

        whatsapp_chat = self.__save_whatsapp_private(hours_since_owner_message = 2)
        self.assertEqual(self.__notify_user().chat, whatsapp_chat)

    def test_stale_whatsapp_window_falls_back_to_telegram_or_fails(self):
        whatsapp_chat = self.__save_whatsapp_private(hours_since_owner_message = 48)
        self.__assert_rejected(NO_PRIVATE_CHAT, 403, lambda: self.__notify_user(), whatsapp_chat)

        telegram_chat = self.__save_telegram_private()
        self.assertEqual(self.__notify_user().chat, telegram_chat)

    def test_group_administrator_notifies_the_group_with_a_prefix(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())

        delivery = self.__notify_chat(group.chat_id.hex)

        self.assertEqual(delivery.chat, group)
        self.assertEqual(self.__sent_texts(group), [f"{USERNAME_PREFIX}Build finished"])

    def test_own_private_chat_by_id_includes_the_sender_and_host(self):
        chat = self.__save_telegram_private()

        self.__notify_chat(chat.chat_id.hex)

        self.assertEqual(self.__sent_texts(chat), [USERNAME_PREFIX + "Build finished"])

    def test_chat_notifications_require_admin_rights(self):
        other_private = self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = "987654321"))
        member_group = self.__save_group(stubs.external.telegram_chat_member(), external_id = "member-group")
        stranger_group = self.__save_group(stubs.external.telegram_chat_member_left(), external_id = "stranger-group")

        self.__assert_rejected(NOT_CHAT_ADMIN, 403, lambda: self.__notify_chat(member_group.chat_id), member_group)
        self.__assert_rejected(NOT_CHAT_MEMBER, 403, lambda: self.__notify_chat(stranger_group.chat_id), stranger_group)
        self.__assert_rejected(NOT_CHAT_MEMBER, 403, lambda: self.__notify_chat(other_private.chat_id), other_private)

    def test_unknown_and_malformed_chat_ids_are_rejected(self):
        self.__assert_rejected(CHAT_NOT_FOUND, 404, lambda: self.__notify_chat(uuid4().hex))
        self.__assert_rejected(MALFORMED_CHAT_ID, 422, lambda: self.__notify_chat("not-a-chat-id"))

    def test_prefix_identity_falls_back_from_username_to_telegram_id(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        no_username = replace(self.owner, telegram_username = None)

        self.__notify_chat(group.chat_id, user = no_username)

        self.assertEqual(self.__sent_texts(group), ["🖥️  [123456789@laptop] Build finished"])

    def test_forged_prefix_inside_the_message_stays_after_the_real_prefix(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())

        self.__notify_chat(group.chat_id, "[someone_else@host] hi")

        self.assertEqual(self.__sent_texts(group), [f"{USERNAME_PREFIX}[someone_else@host] hi"])

    def test_message_exactly_at_the_limit_is_delivered_unchanged(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        limit = 4096
        message = "a" * (limit - measure_text_message_length(USERNAME_PREFIX, ChatConfigDB.ChatType.telegram))
        self.assertEqual(measure_text_message_length(USERNAME_PREFIX + message, ChatConfigDB.ChatType.telegram), limit)

        self.__notify_chat(group.chat_id, message)

        self.assertEqual(self.__sent_texts(group), [USERNAME_PREFIX + message])

    def test_group_message_over_the_limit_keeps_the_prefix_and_ends_with_an_ellipsis(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())

        self.__notify_chat(group.chat_id, "a" * MAX_NOTIFICATION_LENGTH)

        [text] = self.__sent_texts(group)
        kept = text.removeprefix(USERNAME_PREFIX).removesuffix("…")
        telegram = ChatConfigDB.ChatType.telegram
        self.assertTrue(text.startswith(USERNAME_PREFIX + "a"))
        self.assertTrue(text.endswith("a…"))
        self.assertEqual(kept, "a" * len(kept))
        self.assertLessEqual(measure_text_message_length(text, telegram), 4096)
        self.assertGreater(measure_text_message_length(USERNAME_PREFIX + "a" * (len(kept) + 1) + "…", telegram), 4096)

    def test_truncation_never_leaves_whitespace_before_the_ellipsis(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        head_budget = 4096 - measure_text_message_length(USERNAME_PREFIX, ChatConfigDB.ChatType.telegram) - len("…")
        message = "x" * (head_budget - 1) + " " + "y" * 20

        self.__notify_chat(group.chat_id, message)

        self.assertEqual(self.__sent_texts(group), [USERNAME_PREFIX + "x" * (head_budget - 1) + "…"])

    def test_telegram_limit_uses_the_rendered_length(self):
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        message = "*ab*" * 1024

        self.__notify_chat(group.chat_id, message)

        self.assertEqual(self.__sent_texts(group), [USERNAME_PREFIX + message])

    def test_private_chat_message_at_the_maximum_keeps_the_prefix_and_is_cut(self):
        chat = self.__save_telegram_private()

        self.__notify_user("a" * MAX_NOTIFICATION_LENGTH)

        [text] = self.__sent_texts(chat)
        self.assertTrue(text.startswith(USERNAME_PREFIX + "a"))
        self.assertTrue(text.endswith("a…"))
        self.assertLessEqual(measure_text_message_length(text, ChatConfigDB.ChatType.telegram), MAX_NOTIFICATION_LENGTH)

    def test_paid_delivery_is_charged_and_recorded(self):
        chat = self.__save_whatsapp_private(hours_since_owner_message = 1)

        delivery = self.__notify_user()

        [record] = self.__delivery_records()
        self.assertEqual(record.chat_id, chat.chat_id)
        self.assertAlmostEqual(record.total_cost_credits, 0.7)
        self.assertAlmostEqual(delivery.user.credit_balance, self.owner.credit_balance - 0.7)

    def test_free_delivery_leaves_the_balance_unchanged(self):
        self.__save_telegram_private()

        delivery = self.__notify_user()

        self.assertEqual(delivery.user.credit_balance, self.owner.credit_balance)
        self.assertEqual(self.__delivery_records(), [])

    def test_unfunded_owner_cannot_send(self):
        chat = self.__save_whatsapp_private(hours_since_owner_message = 1)
        poor_owner = self.di.user_repo.save(replace(self.owner, credit_balance = 0.5))

        with self.assertRaises(ServiceError) as context:
            self.__notify_user(user = poor_owner)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(context.exception.http_status, 422)
        self.assertEqual(self.__sent_texts(chat), [])
        self.assertEqual(self.__balance(), 0.5)
        self.assertEqual(self.__delivery_records(), [])

    def test_group_pre_flight_covers_every_member(self):
        self.__set_pricing(telegram = "0.3", whatsapp = "0.7")
        group = self.__save_group(stubs.external.telegram_chat_administrator())
        for index in range(3):
            member = self.di.user_repo.save(stubs.domain.user(
                id = None, connect_key = f"MEMBER-KEY-{index}", telegram_user_id = 8000 + index,
                telegram_chat_id = str(8000 + index), whatsapp_user_id = f"551100{index}",
            ))
            self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = member.id, chat_id = group.chat_id))
        poor_owner = self.di.user_repo.save(replace(self.owner, credit_balance = 0.5))

        with self.assertRaises(ServiceError) as context:
            self.__notify_chat(group.chat_id, user = poor_owner)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.__sent_texts(group), [])

    def test_provider_failures_become_a_delivery_failure_and_leave_no_trace(self):
        telegram_chat = self.__save_telegram_private()
        whatsapp_chat = self.__save_whatsapp_private(hours_since_owner_message = 1)
        provider_error = stubs.external.provider_http_error
        cases: list[tuple[str, ChatConfig, Exception]] = [
            ("telegram refusal", telegram_chat, provider_error(403, {"ok": False, "description": "Forbidden"})),
            ("telegram html body", telegram_chat, provider_error(502, "<html>Bad Gateway</html>")),
            ("telegram timeout", telegram_chat, Timeout("timed out")),
            ("whatsapp refusal", whatsapp_chat, provider_error(400, {"error": {"code": 131047}})),
        ]
        for name, chat, error in cases:
            with self.subTest(name = name):
                self.telegram.delivery_errors.clear()
                self.whatsapp.delivery_errors.clear()
                is_whatsapp = chat.chat_type == ChatConfigDB.ChatType.whatsapp
                (self.whatsapp if is_whatsapp else self.telegram).delivery_errors[str(chat.external_id)] = error

                self.__assert_rejected(
                    NOTIFICATION_DELIVERY_FAILED,
                    502,
                    lambda chat = chat: self.__notify_chat(chat.chat_id),
                    telegram_chat,
                    whatsapp_chat,
                )

                agent_id = resolve_agent_user(chat.chat_type).id
                stored = self.di.chat_message_repo.get_latest_by_chat(chat.chat_id, limit = 10)
                self.assertEqual([message for message in stored if message.author_id == agent_id], [])
                self.assertEqual(self.__delivery_records(), [])

    def test_success_identifies_the_chat_and_is_recorded_as_an_agent_message(self):
        chat = self.__save_telegram_private()

        delivery = self.__notify_user()

        self.assertEqual(delivery.chat, chat)
        [message] = self.di.chat_message_repo.get_latest_by_chat(chat.chat_id, limit = 10)
        self.assertEqual(message.author_id, resolve_agent_user(chat.chat_type).id)
        self.assertEqual(message.text, USERNAME_PREFIX + "Build finished")
