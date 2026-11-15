import io
import re
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from util.di_utils import di_for_tests

from api.auth import verify_jwt_token
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.usage.usage_record import UsageRecord
from features.chat.config.chat_config import ChatConfig
from features.cli.cli_access_service import CliAccessService
from features.connect.connect_key_resolver import require_user_by_connect_key
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from features.users.user import User
from util.config import config
from util.error_codes import CLI_TTL_TOO_LONG, CONNECT_KEY_NOT_FOUND, INVALID_CLI_DEVICE, INVALID_CLI_TTL
from util.errors import BadRequestError, NotFoundError, ServiceError, ValidationError

DEVICE_ID = "33333333-3333-4333-8333-333333333333"
KEY_FORMAT = re.compile(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}")
ALERT_TEXT = "Heads up: a new CLI just connected."


def connect_as_the_route_does(
    di: DI,
    connect_key: str,
    ttl_as_text: str | None,
    device_id: str,
    hostname: str,
    os: str,
) -> CliAccessService.Connection:
    owner = require_user_by_connect_key(connect_key, di.db)
    owner_di = di.clone(invoker_id = owner.id.hex)
    owner_di.inject_invoker(owner)
    return owner_di.cli_access_service.connect(ttl_as_text, device_id, hostname, os)


class CliAccessServiceConnectTest(TestCase):

    di: DI
    owner: User
    telegram: FakeTelegramBotAPI
    whatsapp: FakeWhatsAppBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.owner = self.di.user_repo.save(stubs.domain.user())
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)

    def __connect(
        self,
        connect_key: str | None = None,
        ttl_as_text: str | None = None,
        device_id: str = DEVICE_ID,
        hostname: str = "laptop",
        os: str = "darwin",
    ) -> CliAccessService.Connection:
        return connect_as_the_route_does(self.di, connect_key or self.owner.connect_key, ttl_as_text, device_id, hostname, os)

    def __stored_owner(self) -> User:
        return self.di.authorization_service.validate_user(self.owner.id)

    def __revoke_all(self) -> None:
        self.di.clone(invoker_id = self.owner.id.hex).cli_access_service.revoke_all()

    def test_connect_issues_a_token_for_the_owner(self):
        before = datetime.now(timezone.utc)

        connection = self.__connect(ttl_as_text = "90m", device_id = DEVICE_ID.upper(), hostname = "build-box-01")

        claims = verify_jwt_token(connection.token)
        self.assertEqual(claims["sub"], self.owner.id.hex)
        self.assertEqual(claims["scope"], "cli")
        self.assertEqual(claims["cli_generation"], self.owner.cli_token_generation)
        self.assertEqual(claims["device_id"], DEVICE_ID)
        self.assertEqual(claims["hostname"], "build-box-01")
        self.assertEqual(claims["os"], "darwin")
        self.assertEqual(claims["iss"], config.agent_bot_name)
        self.assertEqual(claims["version"], config.version)
        self.assertEqual(connection.user.id, self.owner.id)
        self.assertLessEqual(abs(claims["exp"] - connection.expires_at.timestamp()), 1)
        self.assertEqual(connection.expires_at.tzinfo, timezone.utc)
        self.assertAlmostEqual(
            (connection.expires_at - before).total_seconds(),
            timedelta(minutes = 90).total_seconds(),
            delta = 5,
        )

    def test_connect_rotates_the_key_and_old_key_stops_working(self):
        old_key = self.owner.connect_key

        self.__connect()

        new_key = self.__stored_owner().connect_key
        self.assertNotEqual(new_key, old_key)
        self.assertRegex(new_key, KEY_FORMAT)
        with self.assertRaises(NotFoundError) as context:
            self.__connect(connect_key = old_key)
        self.assertEqual(context.exception.error_code, CONNECT_KEY_NOT_FOUND)

    def test_connect_with_a_key_rotated_after_resolution_fails_and_changes_nothing(self):
        stale_di = self.di.clone(invoker_id = self.owner.id.hex)
        stale_di.inject_invoker(require_user_by_connect_key(self.owner.connect_key, self.di.db))
        self.di.user_repo.update_locked(self.owner.id, lambda user: replace(user, connect_key = "ROTATED-KEY-0001"))

        with self.assertRaises(NotFoundError) as context:
            stale_di.cli_access_service.connect(None, DEVICE_ID, "laptop", "darwin")

        self.assertEqual(context.exception.error_code, CONNECT_KEY_NOT_FOUND)
        self.assertEqual(self.__stored_owner().connect_key, "ROTATED-KEY-0001")

    def test_rejected_connects_change_nothing_and_send_nothing(self):
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = str(self.owner.telegram_user_id)))
        cases: list[tuple[dict[str, str | None], type[ServiceError], int]] = [
            ({"ttl_as_text": "1h30m"}, BadRequestError, INVALID_CLI_TTL),
            ({"ttl_as_text": "3y"}, BadRequestError, CLI_TTL_TOO_LONG),
            ({"device_id": "not-a-uuid"}, ValidationError, INVALID_CLI_DEVICE),
            ({"device_id": ""}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": ""}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "   "}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "a b"}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "[a]"}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "a@b"}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "host\nname"}, ValidationError, INVALID_CLI_DEVICE),
            ({"hostname": "h" * 33}, ValidationError, INVALID_CLI_DEVICE),
            ({"os": ""}, ValidationError, INVALID_CLI_DEVICE),
            ({"os": "dar win"}, ValidationError, INVALID_CLI_DEVICE),
            ({"os": "o" * 33}, ValidationError, INVALID_CLI_DEVICE),
        ]
        for overrides, error_type, error_code in cases:
            with self.subTest(overrides = overrides):
                with self.assertRaises(error_type) as context:
                    self.__connect(**overrides)  # type: ignore[arg-type]
                self.assertEqual(context.exception.error_code, error_code)
                self.assertEqual(self.__stored_owner(), self.owner)
        self.assertEqual(self.telegram.get_sent_messages(str(chat.external_id)), [])

    def test_two_devices_hold_valid_tokens_at_the_same_time(self):
        first = self.__connect(hostname = "first")
        second = self.__connect(connect_key = self.__stored_owner().connect_key, hostname = "second")

        generation = self.__stored_owner().cli_token_generation
        for connection, hostname in ((first, "first"), (second, "second")):
            claims = verify_jwt_token(connection.token)
            self.assertEqual(claims["hostname"], hostname)
            self.assertEqual(claims["cli_generation"], generation)

    def test_connect_is_not_gated_by_onboarding_state(self):
        states = [
            {"is_on_waitlist": True, "is_invited_to_start": False, "are_policies_accepted": False},
            {"is_on_waitlist": False, "is_invited_to_start": False, "are_policies_accepted": False},
        ]
        for index, state in enumerate(states):
            with self.subTest(state = state):
                user = self.di.user_repo.save(stubs.domain.user(
                    id = None, connect_key = f"ONBOARD-KEY-{index}", telegram_user_id = 5000 + index,
                    whatsapp_user_id = f"551100000{index}", **state,
                ))
                connection = self.__connect(connect_key = user.connect_key)
                self.assertEqual(connection.user.id, user.id)

    def test_connect_logs_no_secrets(self):
        self.addCleanup(setattr, config, "log_level", config.log_level)
        config.log_level = "local"
        old_key = self.owner.connect_key
        output = io.StringIO()

        with redirect_stdout(output), redirect_stderr(output):
            connection = self.__connect()
            with self.assertRaises(NotFoundError):
                self.__connect(connect_key = old_key)

        self.assertIn("CLI connected", output.getvalue())
        self.assertNotIn(connection.token, output.getvalue())
        self.assertNotIn(old_key, output.getvalue())
        self.assertNotIn(self.__stored_owner().connect_key, output.getvalue())

    def test_revoke_all_counts_every_call_and_leaves_other_users_alone(self):
        other = self.di.user_repo.save(stubs.domain.user(
            id = None, connect_key = "OTHER-KEY-0001", telegram_user_id = 7001, whatsapp_user_id = "5511000007001",
        ))
        self.__connect()
        self.assertEqual(self.__stored_owner().cli_token_generation, 0)

        self.__revoke_all()
        self.__connect(connect_key = self.__stored_owner().connect_key)
        self.__revoke_all()

        self.assertEqual(self.__stored_owner().cli_token_generation, 2)
        self.assertEqual(self.di.authorization_service.validate_user(other.id).cli_token_generation, 0)


class CliAccessServiceAlertTest(TestCase):

    di: DI
    owner: User
    telegram: FakeTelegramBotAPI
    whatsapp: FakeWhatsAppBotAPI
    model: FakeChatModel

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.owner = self.di.user_repo.save(stubs.domain.user())
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.di.inject_invoker(self.owner)
        tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(tool))
        self.model.responses.append(stubs.external.ai_message(content = ALERT_TEXT))
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "platform-pricing.yaml"
        path.write_text("""\
platforms:
  telegram:
    markets:
      global: {default: true, categories: {service: "0"}}
  whatsapp:
    markets:
      global: {default: true, categories: {service: "0.7"}}
""")
        self.addCleanup(
            setattr,
            config,
            "integration_delivery_pricing_config_path",
            config.integration_delivery_pricing_config_path,
        )
        config.integration_delivery_pricing_config_path = str(path)

    def __connect(self) -> CliAccessService.Connection:
        return connect_as_the_route_does(self.di, self.owner.connect_key, "30d", DEVICE_ID, "laptop", "darwin")

    def __save_telegram_chat(self) -> ChatConfig:
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = str(self.owner.telegram_user_id)))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = self.owner.id, chat_id = chat.chat_id))
        return chat

    def __save_whatsapp_chat(self, hours_since_owner_message: float) -> ChatConfig:
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = UUID("33333333-3333-4333-8333-c33333333333"),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = self.owner.whatsapp_user_id,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = self.owner.id, chat_id = chat.chat_id))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = self.owner.id,
            sent_at = datetime.now() - timedelta(hours = hours_since_owner_message),
            ingestion_order = None,
        ))
        return chat

    def __delivery_records(self) -> list[UsageRecord]:
        return [
            record for record in self.di.usage_record_repo.get_by_user(self.owner.id)
            if record.tool_purpose == ToolType.message_delivery
        ]

    def test_alert_is_the_announcement_about_the_new_device(self):
        chat = self.__save_telegram_chat()

        connection = self.__connect()

        [message] = self.telegram.get_sent_messages(str(chat.external_id))
        self.assertEqual(message["text"], ALERT_TEXT)
        [raw_information] = [prompt[-1].content for prompt in self.model.prompts]
        for expected in ("laptop", "darwin", connection.expires_at.strftime("%Y-%m-%d %H:%M"), "settings", "revoke all CLI access"):  # ruff: ignore[line-too-long]
            self.assertIn(expected, raw_information)

    def test_alert_reaches_whatsapp_only_owner_inside_the_window(self):
        chat = self.__save_whatsapp_chat(hours_since_owner_message = 2)

        self.__connect()

        self.assertEqual(len(self.whatsapp.get_sent_messages(str(chat.external_id))), 1)

    def test_no_alert_when_no_chat_can_receive_it(self):
        stale_chat = self.__save_whatsapp_chat(hours_since_owner_message = 48)

        connection = self.__connect()

        self.assertEqual(self.whatsapp.get_sent_messages(str(stale_chat.external_id)), [])
        self.assertEqual(connection.user.credit_balance, self.owner.credit_balance)
        self.assertEqual(self.model.prompts, [])
        self.assertTrue(self.__stored_key_changed())

    def test_no_alert_when_the_owner_cannot_fund_the_delivery(self):
        chat = self.__save_whatsapp_chat(hours_since_owner_message = 2)
        self.di.user_repo.save(stubs.domain.user(id = self.owner.id, credit_balance = 0.0))

        connection = self.__connect()

        self.assertEqual(self.whatsapp.get_sent_messages(str(chat.external_id)), [])
        self.assertEqual(connection.user.credit_balance, 0.0)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.__delivery_records(), [])

    def test_provider_failure_does_not_fail_the_connect(self):
        chat = self.__save_telegram_chat()
        self.telegram.delivery_errors[str(chat.external_id)] = stubs.external.provider_http_error(
            500, {"ok": False, "description": "Internal Server Error"},
        )

        connection = self.__connect()

        self.assertEqual(self.telegram.get_sent_messages(str(chat.external_id)), [])
        self.assertTrue(connection.token)
        self.assertTrue(self.__stored_key_changed())

    def test_alert_is_billed_like_any_delivery(self):
        chat = self.__save_whatsapp_chat(hours_since_owner_message = 2)

        connection = self.__connect()

        self.assertEqual(len(self.whatsapp.get_sent_messages(str(chat.external_id))), 1)
        [record] = self.__delivery_records()
        self.assertAlmostEqual(record.total_cost_credits, 0.7)
        self.assertAlmostEqual(connection.user.credit_balance, self.owner.credit_balance - 0.7)

    def test_free_alert_leaves_the_balance_unchanged(self):
        self.__save_telegram_chat()

        connection = self.__connect()

        self.assertEqual(connection.user.credit_balance, self.owner.credit_balance)
        self.assertEqual(self.__delivery_records(), [])

    def __stored_key_changed(self) -> bool:
        return self.di.authorization_service.validate_user(self.owner.id).connect_key != self.owner.connect_key


class CliAccessServiceLifetimeTest(TestCase):

    di: DI
    owner: User
    now: datetime

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.owner = self.di.user_repo.save(stubs.domain.user())
        self.now = datetime(2026, 11, 14, 10, 30, 15, tzinfo = timezone.utc)

    def __expiry(self, ttl_as_text: str | None, now: datetime | None = None) -> datetime:
        fixed_now = now or self.now

        class FixedDatetime(datetime):

            @classmethod
            def now(cls, tz = None):
                return fixed_now

        with patch("features.cli.cli_access_service.datetime", FixedDatetime):
            key = self.di.authorization_service.validate_user(self.owner.id).connect_key
            return connect_as_the_route_does(self.di, key, ttl_as_text, DEVICE_ID, "laptop", "darwin").expires_at

    def __assert_rejected(self, ttl_as_text: str | None, error_code: int, now: datetime | None = None):
        with self.assertRaises(BadRequestError) as context:
            self.__expiry(ttl_as_text, now)
        self.assertEqual(context.exception.http_status, 400)
        self.assertEqual(context.exception.error_code, error_code)

    def test_accepted_units(self):
        cases = {
            "90s": self.now + timedelta(seconds = 90),
            "90m": self.now + timedelta(minutes = 90),
            "90min": self.now + timedelta(minutes = 90),
            "12h": self.now + timedelta(hours = 12),
            "30d": self.now + timedelta(days = 30),
            "3M": datetime(2027, 2, 14, 10, 30, 15, tzinfo = timezone.utc),
            "3mo": datetime(2027, 2, 14, 10, 30, 15, tzinfo = timezone.utc),
            "1y": datetime(2027, 11, 14, 10, 30, 15, tzinfo = timezone.utc),
        }
        for ttl_as_text, expected in cases.items():
            with self.subTest(ttl_as_text = ttl_as_text):
                self.assertEqual(self.__expiry(ttl_as_text), expected)

    def test_minutes_and_months_are_different_units(self):
        self.assertEqual(self.__expiry("5m"), self.now + timedelta(minutes = 5))
        self.assertEqual(self.__expiry("5M"), datetime(2027, 4, 14, 10, 30, 15, tzinfo = timezone.utc))

    def test_days_are_exact_hours(self):
        self.assertEqual(self.__expiry("2d") - self.now, timedelta(hours = 48))

    def test_malformed_lifetimes_are_rejected(self):
        cases = [
            "1h30m", "1.5h", "0d", "03d", "-5m", "+5m", "5", "d", "5 d", " 5d", "5d ", "5d\n", "5D", "5days", "1e3s",
            "", "   ", "٣d", "mo", "5M5",
        ]
        for ttl_as_text in cases:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, INVALID_CLI_TTL)

    def test_default_is_six_calendar_months(self):
        self.assertEqual(self.__expiry(None), datetime(2027, 5, 14, 10, 30, 15, tzinfo = timezone.utc))

    def test_maximum_is_accepted(self):
        expected = datetime(2028, 11, 14, 10, 30, 15, tzinfo = timezone.utc)
        self.assertEqual(self.__expiry("2y"), expected)
        self.assertEqual(self.__expiry("24mo"), expected)

    def test_beyond_the_maximum_is_rejected(self):
        for ttl_as_text in ["3y", "25mo", "800d"]:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, CLI_TTL_TOO_LONG)

    def test_cap_is_measured_on_the_calendar(self):
        with_leap_day = datetime(2026, 11, 14, tzinfo = timezone.utc)
        self.assertEqual(self.__expiry("731d", with_leap_day), with_leap_day + timedelta(days = 731))
        self.__assert_rejected("732d", CLI_TTL_TOO_LONG, with_leap_day)

        without_leap_day = datetime(2025, 3, 1, tzinfo = timezone.utc)
        self.assertEqual(self.__expiry("730d", without_leap_day), without_leap_day + timedelta(days = 730))
        self.__assert_rejected("731d", CLI_TTL_TOO_LONG, without_leap_day)

    def test_unrepresentable_lifetimes_are_too_long(self):
        for ttl_as_text in ["99999999999999999999d", "999999999d", "999999999y", "999999999mo", "999999999s"]:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, CLI_TTL_TOO_LONG)

    def test_unrepresentable_expiry_near_the_calendar_end_is_too_long(self):
        self.__assert_rejected("1y", CLI_TTL_TOO_LONG, datetime(9999, 6, 1, tzinfo = timezone.utc))

    def test_month_end_is_clamped(self):
        now = datetime(2027, 1, 31, 8, 0, tzinfo = timezone.utc)
        self.assertEqual(self.__expiry("1mo", now), datetime(2027, 2, 28, 8, 0, tzinfo = timezone.utc))

    def test_leap_day_anniversary_is_clamped(self):
        now = datetime(2028, 2, 29, 8, 0, tzinfo = timezone.utc)
        self.assertEqual(self.__expiry("1y", now), datetime(2029, 2, 28, 8, 0, tzinfo = timezone.utc))

    def test_messages_state_grammar_and_maximum(self):
        with self.assertRaises(BadRequestError) as invalid:
            self.__expiry("nope")
        with self.assertRaises(BadRequestError) as too_long:
            self.__expiry("3y")

        self.assertIn("12h", str(invalid.exception))
        self.assertIn("2 years", str(too_long.exception))
