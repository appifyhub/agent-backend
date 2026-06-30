import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

from pydantic import SecretStr

from api.authorization_service import AuthorizationService
from api.usage_controller import UsageController
from db.model.user import UserDB
from di.di import DI
from features.accounting.usage.usage_aggregates import AggregateStats, ProviderInfo, ToolInfo, UsageAggregates
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_record_repo import UsageRecordRepository
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_4O
from features.users.user import User
from util.error_codes import NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class UsageControllerTest(unittest.TestCase):

    invoker_user: User
    target_user: User
    mock_di: DI
    mock_authorization_service: AuthorizationService
    mock_usage_record_repo: UsageRecordRepository

    def setUp(self):
        self.invoker_user = User(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
            open_ai_key = SecretStr("test_openai_key"),
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )
        self.target_user = User(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
            open_ai_key = SecretStr("test_openai_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        self.mock_di = MagicMock(spec = DI)
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = self.invoker_user)

        self.mock_authorization_service = MagicMock(spec = AuthorizationService)
        self.mock_authorization_service.authorize_for_user.return_value = self.invoker_user
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = self.mock_authorization_service

        self.mock_usage_record_repo = MagicMock(spec = UsageRecordRepository)
        # noinspection PyPropertyAccess
        self.mock_di.usage_record_repo = self.mock_usage_record_repo

    def _create_usage_record(
        self,
        user_id: UUID,
        total_cost: float = 1.0,
        timestamp: datetime | None = None,
    ) -> UsageRecord:
        return UsageRecord(
            user_id = user_id,
            payer_id = user_id,
            chat_id = UUID(int = 1),
            tool = GPT_4O,
            tool_purpose = ToolType.chat,
            timestamp = timestamp or datetime.now(timezone.utc),
            runtime_seconds = 1.5,
            remote_runtime_seconds = 0.5,
            model_cost_credits = 0.1,
            remote_runtime_cost_credits = 0.2,
            api_call_cost_credits = 0.3,
            maintenance_fee_credits = 0.4,
            total_cost_credits = total_cost,
            input_tokens = 100,
            output_tokens = 200,
            search_tokens = 50,
            total_tokens = 350,
            output_image_sizes = [],
            input_image_sizes = [],
        )

    def test_fetch_usage_records_success(self):
        records = [self._create_usage_record(self.invoker_user.id)]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(self.invoker_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, self.invoker_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user, self.invoker_user.id.hex,
        )
        self.mock_usage_record_repo.get_by_user.assert_called_once()

    def test_fetch_usage_records_with_pagination(self):
        records = [self._create_usage_record(self.invoker_user.id, total_cost = i) for i in range(5)]
        self.mock_usage_record_repo.get_by_user.return_value = records[2:4]

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(
            self.invoker_user.id.hex,
            skip = 2,
            limit = 2,
        )

        self.assertEqual(len(result), 2)
        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            self.invoker_user.id,
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
        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        records = [self._create_usage_record(self.invoker_user.id)]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(
            self.invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.assertEqual(len(result), 1)
        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            self.invoker_user.id,
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
        self.mock_usage_record_repo.get_by_user.return_value = []

        controller = UsageController(self.mock_di)
        controller.fetch_usage_records(
            self.invoker_user.id.hex,
            exclude_self = True,
            include_sponsored = True,
        )

        self.mock_usage_record_repo.get_by_user.assert_called_once_with(
            self.invoker_user.id,
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
        self.mock_usage_record_repo.get_by_user.return_value = []

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(self.invoker_user.id.hex)

        self.assertEqual(len(result), 0)

    def test_fetch_usage_records_limit_exceeds_maximum(self):
        controller = UsageController(self.mock_di)

        with self.assertRaises(ValidationError) as context:
            controller.fetch_usage_records(self.invoker_user.id.hex, limit = 101)

        self.assertIn("limit cannot exceed 100", str(context.exception))
        self.mock_authorization_service.authorize_for_user.assert_not_called()
        self.mock_usage_record_repo.get_by_user.assert_not_called()

    def test_fetch_usage_records_authorization_failure(self):
        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = UsageController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_usage_records(self.target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_usage_record_repo.get_by_user.assert_not_called()

    def test_fetch_usage_records_for_other_user(self):
        self.mock_authorization_service.authorize_for_user.return_value = self.target_user
        records = [self._create_usage_record(self.target_user.id)]
        self.mock_usage_record_repo.get_by_user.return_value = records

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_records(self.target_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, self.target_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user, self.target_user.id.hex,
        )

    def test_fetch_usage_aggregates_success(self):
        aggregates = UsageAggregates(
            total_records = 10,
            total_cost_credits = 100.0,
            total_runtime_seconds = 15.0,
            by_tool = {"gpt-4o": AggregateStats(record_count = 10, total_cost = 100.0)},
            by_purpose = {"chat": AggregateStats(record_count = 10, total_cost = 100.0)},
            by_provider = {"open-ai": AggregateStats(record_count = 10, total_cost = 100.0)},
            all_tools_used = [ToolInfo(id = "gpt-4o", name = "GPT 4o")],
            all_purposes_used = ["chat"],
            all_providers_used = [ProviderInfo(id = "open-ai", name = "OpenAI")],
        )
        self.mock_usage_record_repo.get_aggregates_by_user.return_value = aggregates

        controller = UsageController(self.mock_di)
        result = controller.fetch_usage_aggregates(self.invoker_user.id.hex)

        self.assertEqual(result.total_records, 10)
        self.assertEqual(result.total_cost_credits, 100.0)
        self.assertEqual(result.total_runtime_seconds, 15.0)
        self.assertIn("gpt-4o", result.by_tool)
        self.assertIn("chat", result.by_purpose)
        self.assertIn("open-ai", result.by_provider)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user, self.invoker_user.id.hex,
        )

    def test_fetch_usage_aggregates_with_date_filters(self):
        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        aggregates = UsageAggregates(
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
            self.invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.mock_usage_record_repo.get_aggregates_by_user.assert_called_once_with(
            self.invoker_user.id,
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
        aggregates = UsageAggregates(
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
            self.invoker_user.id.hex,
            exclude_self = True,
            include_sponsored = True,
        )

        self.mock_usage_record_repo.get_aggregates_by_user.assert_called_once_with(
            self.invoker_user.id,
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
        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = UsageController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_usage_aggregates(self.target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_usage_record_repo.get_aggregates_by_user.assert_not_called()

    def test_fetch_usage_aggregates_empty_result(self):
        aggregates = UsageAggregates(
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
        result = controller.fetch_usage_aggregates(self.invoker_user.id.hex)

        self.assertEqual(result.total_records, 0)
        self.assertEqual(result.total_cost_credits, 0.0)
        self.assertEqual(result.total_runtime_seconds, 0.0)
        self.assertEqual(len(result.by_tool), 0)
        self.assertEqual(len(result.all_tools_used), 0)
