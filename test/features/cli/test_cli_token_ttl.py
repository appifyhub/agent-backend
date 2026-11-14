from datetime import datetime, timedelta, timezone
from unittest import TestCase

from dateutil.relativedelta import relativedelta

from features.cli.cli_token_ttl import DEFAULT_CLI_TOKEN_TTL, resolve_cli_token_expiry
from util.error_codes import CLI_TTL_TOO_LONG, INVALID_CLI_TTL
from util.errors import BadRequestError


class CliTokenTtlTest(TestCase):

    now: datetime

    def setUp(self):
        self.now = datetime(2026, 11, 14, 10, 30, 15, tzinfo = timezone.utc)

    def __assert_rejected(self, ttl_as_text: str | None, error_code: int, now: datetime | None = None):
        with self.assertRaises(BadRequestError) as context:
            resolve_cli_token_expiry(ttl_as_text, now or self.now)
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
                self.assertEqual(resolve_cli_token_expiry(ttl_as_text, self.now), expected)

    def test_minutes_and_months_are_different_units(self):
        self.assertEqual(resolve_cli_token_expiry("5m", self.now), self.now + timedelta(minutes = 5))
        self.assertEqual(
            resolve_cli_token_expiry("5M", self.now),
            datetime(2027, 4, 14, 10, 30, 15, tzinfo = timezone.utc),
        )

    def test_days_are_exact_hours(self):
        self.assertEqual(resolve_cli_token_expiry("2d", self.now) - self.now, timedelta(hours = 48))

    def test_malformed_lifetimes_are_rejected(self):
        cases = [
            "1h30m", "1.5h", "0d", "03d", "-5m", "+5m", "5", "d", "5 d", " 5d", "5d ", "5d\n", "5D", "5days", "1e3s",
            "", "   ", "٣d", "mo", "5M5",
        ]
        for ttl_as_text in cases:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, INVALID_CLI_TTL)

    def test_default_is_six_calendar_months(self):
        self.assertEqual(DEFAULT_CLI_TOKEN_TTL, relativedelta(months = 6))
        self.assertEqual(
            resolve_cli_token_expiry(None, self.now),
            datetime(2027, 5, 14, 10, 30, 15, tzinfo = timezone.utc),
        )

    def test_maximum_is_accepted(self):
        expected = datetime(2028, 11, 14, 10, 30, 15, tzinfo = timezone.utc)
        self.assertEqual(resolve_cli_token_expiry("2y", self.now), expected)
        self.assertEqual(resolve_cli_token_expiry("24mo", self.now), expected)

    def test_beyond_the_maximum_is_rejected(self):
        for ttl_as_text in ["3y", "25mo", "800d"]:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, CLI_TTL_TOO_LONG)

    def test_cap_is_measured_on_the_calendar(self):
        with_leap_day = datetime(2026, 11, 14, tzinfo = timezone.utc)
        self.assertEqual(resolve_cli_token_expiry("731d", with_leap_day), with_leap_day + timedelta(days = 731))
        self.__assert_rejected("732d", CLI_TTL_TOO_LONG, with_leap_day)

        without_leap_day = datetime(2025, 3, 1, tzinfo = timezone.utc)
        self.assertEqual(resolve_cli_token_expiry("730d", without_leap_day), without_leap_day + timedelta(days = 730))
        self.__assert_rejected("731d", CLI_TTL_TOO_LONG, without_leap_day)

    def test_unrepresentable_lifetimes_are_too_long(self):
        for ttl_as_text in ["99999999999999999999d", "999999999d", "999999999y", "999999999mo", "999999999s"]:
            with self.subTest(ttl_as_text = ttl_as_text):
                self.__assert_rejected(ttl_as_text, CLI_TTL_TOO_LONG)

    def test_unrepresentable_expiry_near_the_calendar_end_is_too_long(self):
        self.__assert_rejected("1y", CLI_TTL_TOO_LONG, datetime(9999, 6, 1, tzinfo = timezone.utc))

    def test_month_end_is_clamped(self):
        now = datetime(2027, 1, 31, 8, 0, tzinfo = timezone.utc)
        self.assertEqual(resolve_cli_token_expiry("1mo", now), datetime(2027, 2, 28, 8, 0, tzinfo = timezone.utc))

    def test_leap_day_anniversary_is_clamped(self):
        now = datetime(2028, 2, 29, 8, 0, tzinfo = timezone.utc)
        self.assertEqual(resolve_cli_token_expiry("1y", now), datetime(2029, 2, 28, 8, 0, tzinfo = timezone.utc))

    def test_messages_state_grammar_and_maximum(self):
        with self.assertRaises(BadRequestError) as invalid:
            resolve_cli_token_expiry("nope", self.now)
        with self.assertRaises(BadRequestError) as too_long:
            resolve_cli_token_expiry("3y", self.now)

        self.assertIn("12h", str(invalid.exception))
        self.assertIn("2 years", str(too_long.exception))
