from datetime import datetime, timezone
from unittest import TestCase
from uuid import UUID

import stubs
from util.di_utils import di_for_tests

from api.usage_controller import UsageController
from di.di import DI
from features.users.user import User
from util.error_codes import INVALID_LIMIT, NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class UsageControllerTest(TestCase):

    di: DI
    controller: UsageController
    user: User
    other: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.other = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None, whatsapp_user_id = None, connect_key = "OTHER-USER",
        ))
        self.di.inject_invoker(self.user)
        self.controller = self.di.usage_controller

    def test_fetch_usage_records_success(self):
        record = self.di.usage_record_repo.create(stubs.domain.usage_record())

        self.assertEqual(self.controller.fetch_usage_records(self.user.id.hex), [record])

    def test_fetch_usage_records_with_pagination(self):
        records = self.di.usage_record_repo.create_all([
            stubs.domain.usage_record(timestamp = datetime(2026, 1, day, tzinfo = timezone.utc))
            for day in range(1, 6)
        ])

        result = self.controller.fetch_usage_records(self.user.id.hex, skip = 2, limit = 2)

        self.assertEqual(result, [records[2], records[1]])

    def test_fetch_usage_records_with_date_filters(self):
        records = self.di.usage_record_repo.create_all([
            stubs.domain.usage_record(timestamp = datetime(2026, 1, day, tzinfo = timezone.utc))
            for day in (1, 15, 31)
        ])

        result = self.controller.fetch_usage_records(
            self.user.id.hex,
            start_date = datetime(2026, 1, 10, tzinfo = timezone.utc),
            end_date = datetime(2026, 1, 20, tzinfo = timezone.utc),
        )

        self.assertEqual(result, [records[1]])

    def test_fetch_usage_records_with_sponsored_flags(self):
        self.di.usage_record_repo.create(stubs.domain.usage_record())
        sponsored = self.di.usage_record_repo.create(stubs.domain.usage_record(user_id = self.other.id))
        self.di.usage_record_repo.create(stubs.domain.usage_record(user_id = self.other.id, payer_id = self.other.id))

        result = self.controller.fetch_usage_records(self.user.id.hex, exclude_self = True, include_sponsored = True)

        self.assertEqual(result, [sponsored])

    def test_fetch_usage_records_empty_result(self):
        self.assertEqual(self.controller.fetch_usage_records(self.user.id.hex), [])

    def test_fetch_usage_records_limit_exceeds_maximum(self):
        with self.assertRaises(ValidationError) as context:
            self.controller.fetch_usage_records(self.user.id.hex, limit = 101)

        self.assertEqual(context.exception.error_code, INVALID_LIMIT)

    def test_fetch_usage_records_authorization_failure(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.fetch_usage_records(self.other.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

    def test_fetch_usage_records_excludes_other_users(self):
        self.di.usage_record_repo.create(stubs.domain.usage_record(user_id = self.other.id, payer_id = self.other.id))

        self.assertEqual(self.controller.fetch_usage_records(self.user.id.hex), [])

    def test_fetch_usage_aggregates_success(self):
        record = self.di.usage_record_repo.create(stubs.domain.usage_record())

        result = self.controller.fetch_usage_aggregates(self.user.id.hex)

        self.assertEqual(result.total_records, 1)
        self.assertEqual(result.total_cost_credits, record.total_cost_credits)
        self.assertEqual(result.total_runtime_seconds, record.runtime_seconds)
        self.assertEqual(result.by_tool[record.tool.id].record_count, 1)
        self.assertEqual(result.by_purpose[record.tool_purpose.value].record_count, 1)
        self.assertEqual(result.by_provider[record.tool.provider.id].record_count, 1)
        self.assertEqual([tool.id for tool in result.all_tools_used], [record.tool.id])
        self.assertEqual(result.all_purposes_used, [record.tool_purpose.value])
        self.assertEqual([provider.id for provider in result.all_providers_used], [record.tool.provider.id])

    def test_fetch_usage_aggregates_with_date_filters(self):
        self.di.usage_record_repo.create_all([
            stubs.domain.usage_record(
                timestamp = datetime(2026, 1, day, tzinfo = timezone.utc), total_cost_credits = float(day),
            )
            for day in (1, 15, 31)
        ])

        result = self.controller.fetch_usage_aggregates(
            self.user.id.hex,
            start_date = datetime(2026, 1, 10, tzinfo = timezone.utc),
            end_date = datetime(2026, 1, 20, tzinfo = timezone.utc),
        )

        self.assertEqual(result.total_records, 1)
        self.assertEqual(result.total_cost_credits, 15.0)

    def test_fetch_usage_aggregates_with_sponsored_flags(self):
        self.di.usage_record_repo.create(stubs.domain.usage_record())
        sponsored = self.di.usage_record_repo.create(stubs.domain.usage_record(user_id = self.other.id))
        self.di.usage_record_repo.create(stubs.domain.usage_record(user_id = self.other.id, payer_id = self.other.id))

        result = self.controller.fetch_usage_aggregates(self.user.id.hex, exclude_self = True, include_sponsored = True)

        self.assertEqual(result.total_records, 1)
        self.assertEqual(result.total_cost_credits, sponsored.total_cost_credits)
        self.assertEqual(result.total_runtime_seconds, sponsored.runtime_seconds)

    def test_fetch_usage_aggregates_authorization_failure(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.fetch_usage_aggregates(self.other.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

    def test_fetch_usage_aggregates_empty_result(self):
        result = self.controller.fetch_usage_aggregates(self.user.id.hex)

        self.assertEqual(result.total_records, 0)
        self.assertEqual(result.total_cost_credits, 0.0)
        self.assertEqual(result.total_runtime_seconds, 0.0)
        self.assertEqual(result.by_tool, {})
        self.assertEqual(result.by_purpose, {})
        self.assertEqual(result.by_provider, {})
        self.assertEqual(result.all_tools_used, [])
        self.assertEqual(result.all_purposes_used, [])
        self.assertEqual(result.all_providers_used, [])
