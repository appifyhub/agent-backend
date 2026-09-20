import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

import stubs

from api.authorization_service import AuthorizationService
from api.usage_controller import UsageController
from di.di import DI
from features.accounting.usage.usage_record_repo import UsageRecordRepository
from util.error_codes import NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class UsageControllerTest(unittest.TestCase):

    mock_di: DI
    mock_authorization_service: AuthorizationService
    mock_usage_record_repo: UsageRecordRepository

    def setUp(self):
        self.mock_di = MagicMock(spec = DI)

        self.mock_authorization_service = MagicMock(spec = AuthorizationService)
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = self.mock_authorization_service

        self.mock_usage_record_repo = MagicMock(spec = UsageRecordRepository)
        # noinspection PyPropertyAccess
        self.mock_di.usage_record_repo = self.mock_usage_record_repo

    def test_fetch_usage_records_success(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        records = [
            stubs.domain.usage_record(user_id = invoker_user.id, payer_id = invoker_user.id),
        ]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(invoker_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, invoker_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            invoker_user, invoker_user.id.hex,
        )
        self.mock_usage_record_repo.get_by_user.assert_called_once()

    def test_fetch_usage_records_with_pagination(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        records = [
            stubs.domain.usage_record(
                user_id = invoker_user.id,
                payer_id = invoker_user.id,
                total_cost_credits = i,
            )
            for i in range(5)
        ]
        self.mock_usage_record_repo.get_by_user.return_value = records[2:4]

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(
            invoker_user.id.hex,
            skip = 2,
            limit = 2,
        )

        self.assertEqual(len(result), 2)
        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 2,
            limit = 2,
            start_date = None,
            end_date = None,
            exclude_self = False,
            include_sponsored = False,
            include_transfers = True,
            only_transfers = False,
            tool_id = None,
            purpose = None,
            provider_id = None,
        )

    def test_fetch_usage_records_with_date_filters(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        records = [
            stubs.domain.usage_record(user_id = invoker_user.id, payer_id = invoker_user.id),
        ]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(
            invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.assertEqual(len(result), 1)
        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = start,
            end_date = end,
            exclude_self = False,
            include_sponsored = False,
            include_transfers = True,
            only_transfers = False,
            tool_id = None,
            purpose = None,
            provider_id = None,
        )

    def test_fetch_usage_records_with_sponsored_flags(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_usage_record_repo.get_by_user.return_value = []

        controller = UsageController(self.mock_di)
        controller.fetch_usage_records(
            invoker_user.id.hex,
            exclude_self = True,
            include_sponsored = True,
        )

        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = None,
            end_date = None,
            exclude_self = True,
            include_sponsored = True,
            include_transfers = True,
            only_transfers = False,
            tool_id = None,
            purpose = None,
            provider_id = None,
        )

    def test_fetch_usage_records_empty_result(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_usage_record_repo.get_by_user.return_value = []

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(invoker_user.id.hex)

        self.assertEqual(len(result), 0)

    def test_fetch_usage_records_limit_exceeds_maximum(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        controller = UsageController(self.mock_di)

        with self.assertRaises(ValidationError) as context:
            controller.fetch_usage_records(invoker_user.id.hex, limit = 101)

        self.assertIn("limit cannot exceed 100", str(context.exception))
        self.mock_authorization_service.authorize_for_user.assert_not_called()
        self.mock_usage_record_repo.get_by_user.assert_not_called()

    def test_fetch_usage_records_authorization_failure(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = UsageController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_usage_records(target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_usage_record_repo.get_by_user.assert_not_called()

    def test_fetch_usage_records_for_other_user(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_authorization_service.authorize_for_user.return_value = target_user
        records = [
            stubs.domain.usage_record(user_id = target_user.id, payer_id = target_user.id),
        ]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(target_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, target_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            invoker_user, target_user.id.hex,
        )

    def test_fetch_usage_aggregates_success(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        aggregates = stubs.domain.usage_aggregates()
        self.mock_usage_record_repo.get_aggregates_by_user.return_value = aggregates

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_aggregates(invoker_user.id.hex)

        self.assertEqual(result.total_records, 10)
        self.assertEqual(result.total_cost_credits, 100.0)
        self.assertEqual(result.total_runtime_seconds, 15.0)
        self.assertIn("gpt-4o", result.by_tool)
        self.assertIn("chat", result.by_purpose)
        self.assertIn("open-ai", result.by_provider)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            invoker_user, invoker_user.id.hex,
        )

    def test_fetch_usage_aggregates_with_date_filters(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        aggregates = stubs.domain.usage_aggregates(
            total_records = 0,
            total_cost_credits = 0.0,
            total_runtime_seconds = 0.0,
            by_tool = {},
            by_purpose = {},
            by_provider = {},
            all_tools_used = [],
            all_purposes_used = [],
            all_providers_used = [],
        )
        self.mock_usage_record_repo.get_aggregates_by_user.return_value = aggregates

        controller = UsageController(self.mock_di)
        controller.fetch_usage_aggregates(
            invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.mock_usage_record_repo.get_aggregates_by_user.assert_called_once_with(
            invoker_user.id,
            start_date = start,
            end_date = end,
            exclude_self = False,
            include_sponsored = False,
            include_transfers = True,
            only_transfers = False,
            tool_id = None,
            purpose = None,
            provider_id = None,
        )

    def test_fetch_usage_aggregates_with_sponsored_flags(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        aggregates = stubs.domain.usage_aggregates(
            total_records = 0,
            total_cost_credits = 0.0,
            total_runtime_seconds = 0.0,
            by_tool = {},
            by_purpose = {},
            by_provider = {},
            all_tools_used = [],
            all_purposes_used = [],
            all_providers_used = [],
        )
        self.mock_usage_record_repo.get_aggregates_by_user.return_value = aggregates

        controller = UsageController(self.mock_di)
        controller.fetch_usage_aggregates(
            invoker_user.id.hex,
            exclude_self = True,
            include_sponsored = True,
        )

        self.mock_usage_record_repo.get_aggregates_by_user.assert_called_once_with(
            invoker_user.id,
            start_date = None,
            end_date = None,
            exclude_self = True,
            include_sponsored = True,
            include_transfers = True,
            only_transfers = False,
            tool_id = None,
            purpose = None,
            provider_id = None,
        )

    def test_fetch_usage_aggregates_authorization_failure(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = UsageController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_usage_aggregates(target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_usage_record_repo.get_aggregates_by_user.assert_not_called()

    def test_fetch_usage_aggregates_empty_result(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
        )
        stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
        )
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        aggregates = stubs.domain.usage_aggregates(
            total_records = 0,
            total_cost_credits = 0.0,
            total_runtime_seconds = 0.0,
            by_tool = {},
            by_purpose = {},
            by_provider = {},
            all_tools_used = [],
            all_purposes_used = [],
            all_providers_used = [],
        )
        self.mock_usage_record_repo.get_aggregates_by_user.return_value = aggregates

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_aggregates(invoker_user.id.hex)

        self.assertEqual(result.total_records, 0)
        self.assertEqual(result.total_cost_credits, 0.0)
        self.assertEqual(result.total_runtime_seconds, 0.0)
        self.assertEqual(len(result.by_tool), 0)
        self.assertEqual(len(result.all_tools_used), 0)
