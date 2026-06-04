import unittest
from datetime import date
from unittest.mock import MagicMock, Mock
from uuid import UUID

from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from util.config import config


class UsageTrackingServiceTest(unittest.TestCase):

    mock_di: DI
    user_id: UUID
    chat_id: UUID
    service: UsageTrackingService

    def setUp(self):
        self.user_id = UUID(int = 1)
        self.chat_id = UUID(int = 2)
        self.payer_id = UUID(int = 3)

        self.mock_di = Mock(spec = DI)
        mock_user = Mock()
        mock_user.id = self.user_id
        self.mock_di.invoker = mock_user

        mock_chat = Mock()
        mock_chat.chat_id = self.chat_id
        self.mock_di.require_invoker_chat = MagicMock(return_value = mock_chat)
        self.mock_di.invoker_chat = mock_chat

        mock_repo = Mock()
        mock_repo.create = MagicMock(side_effect = lambda x: x)
        self.mock_di.usage_record_repo = mock_repo
        self.mock_di.user_crud.get.return_value = None

        self.original_fee = config.usage_maintenance_fee_credits
        config.usage_maintenance_fee_credits = 1.0

        self.service = UsageTrackingService(self.mock_di)

    def tearDown(self):
        config.usage_maintenance_fee_credits = self.original_fee

    def _create_tool(
        self,
        tool_id: str = "test-tool",
        input_1m: int | None = 100,
        output_1m: int | None = 200,
        search_1m: int | None = None,
        output_image_1k: int | None = None,
        output_image_2k: int | None = None,
        output_image_4k: int | None = None,
        input_image_1k: int | None = None,
        input_image_2k: int | None = None,
        input_image_4k: int | None = None,
        api_call: int | None = None,
        second_of_runtime: int | None = None,
    ) -> ExternalTool:
        provider = ExternalToolProvider(
            id = "test-provider",
            name = "Test Provider",
            token_management_url = "https://test.com",
            token_format = "test",
            tools = [],
        )
        cost_estimate = CostEstimate(
            input_1m_tokens = input_1m,
            output_1m_tokens = output_1m,
            search_1m_tokens = search_1m,
            output_image_1k = output_image_1k,
            output_image_2k = output_image_2k,
            output_image_4k = output_image_4k,
            input_image_1k = input_image_1k,
            input_image_2k = input_image_2k,
            input_image_4k = input_image_4k,
            api_call = api_call,
            second_of_runtime = second_of_runtime,
        )
        return ExternalTool(
            id = tool_id,
            name = "Test Tool",
            provider = provider,
            types = [ToolType.chat],
            cost_estimate = cost_estimate,
        )

    def test_track_text_model_with_all_tokens(self):
        tool = self._create_tool(api_call = 10)
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 1000,
            output_tokens = 2000,
            search_tokens = 500,
            total_tokens = 3500,
        )

        self.assertIsInstance(record, UsageRecord)
        self.assertEqual(record.user_id, self.user_id)
        self.assertEqual(record.chat_id, self.chat_id)
        self.assertEqual(record.tool, tool)
        self.assertEqual(record.runtime_seconds, 5)
        self.assertEqual(record.input_tokens, 1000)
        self.assertEqual(record.output_tokens, 2000)
        self.assertEqual(record.search_tokens, 500)
        self.assertEqual(record.total_tokens, 3500)
        # Cost: (1000/1M * 100) + (2000/1M * 200) + (500/1M * 0) = 0.1 + 0.4 = 0.5
        self.assertAlmostEqual(record.model_cost_credits, 0.5, places = 5)
        self.assertEqual(record.api_call_cost_credits, 10.0)
        self.assertEqual(record.maintenance_fee_credits, 1.0)
        self.assertEqual(
            record.total_cost_credits,
            record.model_cost_credits + record.api_call_cost_credits + 1.0,
        )

    def test_track_text_model_with_total_tokens_only(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 3,
            payer_id = self.payer_id,
            uses_credits = False,
            total_tokens = 5000,
        )

        self.assertEqual(record.total_tokens, 5000)
        self.assertIsNone(record.input_tokens)
        self.assertIsNone(record.output_tokens)
        self.assertIsNone(record.search_tokens)
        # Cost should be 0 since no input/output tokens provided
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_text_model_calculates_total_from_components(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 2,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 500,
            output_tokens = 1000,
            total_tokens = 1500,
        )

        self.assertEqual(record.total_tokens, 1500)

    def test_track_text_model_with_search_tokens(self):
        tool = self._create_tool(search_1m = 300)
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 4,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 1000,
            output_tokens = 2000,
            search_tokens = 500,
        )

        # Cost: (1000/1M * 100) + (2000/1M * 200) + (500/1M * 300) = 0.1 + 0.4 + 0.15 = 0.65
        self.assertAlmostEqual(record.model_cost_credits, 0.65, places = 5)

    def test_track_text_model_returns_zero_model_cost_when_all_tokens_none(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_image_model_with_tokens(self):
        tool = self._create_tool(api_call = 5)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 10,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 500,
            output_tokens = 1000,
            total_tokens = 1500,
        )

        self.assertEqual(record.input_tokens, 500)
        self.assertEqual(record.output_tokens, 1000)
        self.assertEqual(record.total_tokens, 1500)
        # Cost calculated using LLM logic: (500/1M * 100) + (1000/1M * 200) = 0.05 + 0.2 = 0.25
        self.assertAlmostEqual(record.model_cost_credits, 0.25, places = 5)
        self.assertEqual(record.api_call_cost_credits, 5.0)
        self.assertEqual(record.maintenance_fee_credits, 1.0)
        self.assertEqual(
            record.total_cost_credits,
            record.model_cost_credits + record.api_call_cost_credits + 1.0,
        )

    def test_track_image_model_with_size_1k(self):
        tool = self._create_tool(output_image_1k = 50)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["1k"],
        )

        self.assertEqual(record.output_image_sizes, ["1k"])
        self.assertEqual(record.model_cost_credits, 50.0)

    def test_track_image_model_with_size_2k(self):
        tool = self._create_tool(output_image_2k = 100)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["2k"],
        )

        self.assertEqual(record.model_cost_credits, 100.0)

    def test_track_image_model_with_size_4k(self):
        tool = self._create_tool(output_image_4k = 200)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["4k"],
        )

        self.assertEqual(record.model_cost_credits, 200.0)

    def test_track_image_model_fallback_to_1k(self):
        tool = self._create_tool(output_image_1k = 50)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["unknown"],
        )

        self.assertEqual(record.model_cost_credits, 50.0)

    def test_track_image_model_normalizes_input_size_formats(self):
        tool = self._create_tool(input_image_1k = 5, input_image_2k = 10, input_image_4k = 20)

        variants_2k = ["2K", "2k", "2M", "2m", "2MB", "2mb", "2MP", "2mp", "2 MP", "2 mb"]
        for size_variant in variants_2k:
            record = self.service.track_image_model(
                tool = tool,
                tool_purpose = ToolType.chat,
                runtime_seconds = 1,
                payer_id = self.payer_id,
                uses_credits = False,
                input_image_sizes = [size_variant],
            )
            self.assertEqual(record.model_cost_credits, 10.0, f"Failed for variant: {size_variant}")

    def test_track_image_model_normalizes_size_formats(self):
        tool = self._create_tool(output_image_1k = 10, output_image_2k = 20, output_image_4k = 40)

        # test various 2K format variants
        variants_2k = [
            "2K", "2k", "2 K", "2 k", "2M", "2m", "2 M", "2 m",
            "2MB", "2mb", "2 MB", "2 mb", "2MP", "2mp", "2 MP", "2 mp",
        ]
        for size_variant in variants_2k:
            record = self.service.track_image_model(
                tool = tool,
                tool_purpose = ToolType.chat,
                runtime_seconds = 1,
                payer_id = self.payer_id,
                uses_credits = False,
                output_image_sizes = [size_variant],
            )
            self.assertEqual(record.model_cost_credits, 20.0, f"Failed for variant: {size_variant}")

        # test 1K variants
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["1 MP"],
        )
        self.assertEqual(record.model_cost_credits, 10.0)

        # test 4K variants
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["4 MB"],
        )
        self.assertEqual(record.model_cost_credits, 40.0)

    def test_track_image_model_calculates_total_from_components(self):
        tool = self._create_tool(output_image_1k = 50)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 3,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 100,
            output_tokens = 200,
            total_tokens = 300,
            output_image_sizes = ["1k"],
        )

        self.assertEqual(record.total_tokens, 300)

    def test_track_image_model_returns_zero_model_cost_when_all_none(self):
        tool = self._create_tool()
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_image_model_returns_zero_model_cost_when_no_pricing(self):
        tool = self._create_tool(output_image_1k = None)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["1k"],
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_api_call(self):
        tool = self._create_tool(api_call = 10)
        record = self.service.track_api_call(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 2,
            payer_id = self.payer_id,
            uses_credits = False,
        )

        self.assertEqual(record.model_cost_credits, 0.0)
        self.assertEqual(record.api_call_cost_credits, 10.0)
        self.assertEqual(record.runtime_seconds, 2)
        self.assertEqual(record.maintenance_fee_credits, 1.0)
        self.assertEqual(
            record.total_cost_credits,
            record.api_call_cost_credits + 1.0,
        )

    def test_track_api_call_with_zero_cost(self):
        tool = self._create_tool(api_call = None)
        record = self.service.track_api_call(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
        )

        self.assertEqual(record.model_cost_credits, 0.0)
        self.assertEqual(record.api_call_cost_credits, 0.0)

    def test_maintenance_fee_included(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 1000,
            total_tokens = 1000,
        )

        self.assertIsInstance(record.maintenance_fee_credits, float)
        self.assertEqual(record.maintenance_fee_credits, 1.0)
        self.assertEqual(
            record.total_cost_credits,
            record.model_cost_credits + 1.0,
        )

    def test_track_text_model_with_zero_tokens(self):
        tool = self._create_tool()
        # Verifies that 0 is treated as a valid value (not treated as None/missing)
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 0,
            output_tokens = 0,
            total_tokens = 0,
        )
        self.assertEqual(record.input_tokens, 0)
        self.assertEqual(record.total_tokens, 0)
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_image_model_with_zero_tokens(self):
        tool = self._create_tool()
        # Verifies that 0 tokens are valid for image tools too
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 0,
            output_tokens = 0,
            total_tokens = 0,
        )
        self.assertEqual(record.input_tokens, 0)
        self.assertEqual(record.total_tokens, 0)
        self.assertEqual(record.model_cost_credits, 0.0)
        self.assertEqual(record.total_tokens, 0)
        self.assertEqual(record.model_cost_credits, 0.0)

    def test_track_text_model_with_remote_runtime_cost(self):
        tool = self._create_tool(second_of_runtime = 5)
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 2,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 1000,
            total_tokens = 1000,
            remote_runtime_seconds = 10.5,
        )
        # Runtime cost: 5 credits/second * 10.5 seconds = 52.5 credits
        self.assertAlmostEqual(record.remote_runtime_cost_credits, 52.5, places = 5)
        # Model cost: (1000/1M * 100) = 0.1
        self.assertAlmostEqual(record.model_cost_credits, 0.1, places = 5)
        # Total = model + runtime + maintenance
        self.assertAlmostEqual(
            record.total_cost_credits,
            0.1 + 52.5 + 1.0,
            places = 5,
        )

    def test_track_image_model_with_remote_runtime_cost(self):
        tool = self._create_tool(output_image_1k = 10, second_of_runtime = 3)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 5,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["1k"],
            remote_runtime_seconds = 8.0,
        )
        # Runtime cost: 3 credits/second * 8.0 seconds = 24.0 credits
        self.assertAlmostEqual(record.remote_runtime_cost_credits, 24.0, places = 5)
        # Model cost: 10 credits for 1k
        self.assertEqual(record.model_cost_credits, 10.0)
        # Total = model + runtime + maintenance
        self.assertAlmostEqual(
            record.total_cost_credits,
            10.0 + 24.0 + 1.0,
            places = 5,
        )

    def test_track_text_model_without_remote_runtime(self):
        tool = self._create_tool(second_of_runtime = 5)
        # default input_1m = 100 in _create_tool. 1000 tokens = 0.1 credits
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 2,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 1000,
            total_tokens = 1000,
            # remote_runtime_seconds not provided (None)
        )
        # Runtime cost should fallback to wall clock runtime_seconds (5 * 2 = 10)
        self.assertEqual(record.remote_runtime_cost_credits, 10.0)
        self.assertEqual(record.total_cost_credits, 0.1 + 10.0 + config.usage_maintenance_fee_credits)

    def test_track_text_model_persists_to_repo(self):
        tool = self._create_tool()
        self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            input_tokens = 100,
            total_tokens = 100,
        )
        self.mock_di.usage_record_repo.create.assert_called_once()

    def test_track_image_model_persists_to_repo(self):
        tool = self._create_tool(output_image_1k = 10)
        self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.images_gen,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
            output_image_sizes = ["1k"],
        )
        self.mock_di.usage_record_repo.create.assert_called_once()

    def test_track_api_call_persists_to_repo(self):
        tool = self._create_tool(api_call = 5)
        self.service.track_api_call(
            tool = tool,
            tool_purpose = ToolType.api_twitter,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = False,
        )
        self.mock_di.usage_record_repo.create.assert_called_once()

    def test_track_text_model_stores_payer_id_and_uses_credits(self):
        payer_id = UUID(int = 99)
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            input_tokens = 100,
            payer_id = payer_id,
            uses_credits = True,
        )
        self.assertEqual(record.payer_id, payer_id)
        self.assertTrue(record.uses_credits)

    def test_track_image_model_stores_payer_id_and_uses_credits(self):
        payer_id = UUID(int = 99)
        tool = self._create_tool(output_image_1k = 10)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.images_gen,
            runtime_seconds = 1,
            output_image_sizes = ["1k"],
            payer_id = payer_id,
            uses_credits = True,
        )
        self.assertEqual(record.payer_id, payer_id)
        self.assertTrue(record.uses_credits)

    def test_track_api_call_stores_payer_id_and_uses_credits(self):
        payer_id = UUID(int = 99)
        tool = self._create_tool(api_call = 5)
        record = self.service.track_api_call(
            tool = tool,
            tool_purpose = ToolType.api_twitter,
            runtime_seconds = 1,
            payer_id = payer_id,
            uses_credits = False,
        )
        self.assertEqual(record.payer_id, payer_id)
        self.assertFalse(record.uses_credits)

    def test_participant_details_regular_usage(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.user_id,
            uses_credits = True,
            input_tokens = 100,
        )
        self.assertIsNotNone(record.participant_details)
        self.assertIsNotNone(record.participant_details.payer)
        self.assertEqual(record.participant_details.payer.user_id, self.user_id)
        self.assertIsNotNone(record.participant_details.owner)
        self.assertEqual(record.participant_details.owner.user_id, self.user_id)
        self.assertIsNone(record.participant_details.counterpart)

    def test_participant_details_sponsored_payer_not_in_db(self):
        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = True,
            input_tokens = 100,
        )
        self.assertIsNotNone(record.participant_details)
        self.assertIsNotNone(record.participant_details.payer)
        self.assertEqual(record.participant_details.payer.user_id, self.payer_id)
        self.assertIsNone(record.participant_details.payer.full_name)
        self.assertIsNone(record.participant_details.payer.platform)
        self.assertIsNotNone(record.participant_details.owner)
        self.assertEqual(record.participant_details.owner.user_id, self.user_id)

    def test_participant_details_sponsored_payer_found_in_db(self):
        payer = User(
            id = self.payer_id,
            full_name = "Payer User",
            telegram_username = "payer_handle",
            group = UserDB.Group.standard,
            created_at = date.today(),
            credit_balance = 50.0,
        )
        self.mock_di.user_crud.get.return_value = payer.model_dump()

        tool = self._create_tool()
        record = self.service.track_text_model(
            tool = tool,
            tool_purpose = ToolType.chat,
            runtime_seconds = 1,
            payer_id = self.payer_id,
            uses_credits = True,
            input_tokens = 100,
        )

        self.assertEqual(record.participant_details.payer.user_id, self.payer_id)
        self.assertEqual(record.participant_details.payer.full_name, "Payer User")
        self.assertIsNotNone(record.participant_details.owner)
        self.assertEqual(record.participant_details.owner.user_id, self.user_id)

    def test_participant_details_image_model(self):
        tool = self._create_tool(output_image_1k = 10)
        record = self.service.track_image_model(
            tool = tool,
            tool_purpose = ToolType.images_gen,
            runtime_seconds = 1,
            payer_id = self.user_id,
            uses_credits = True,
            output_image_sizes = ["1k"],
        )
        self.assertIsNotNone(record.participant_details)
        self.assertIsNotNone(record.participant_details.payer)
        self.assertEqual(record.participant_details.payer.user_id, self.user_id)
        self.assertIsNotNone(record.participant_details.owner)
        self.assertEqual(record.participant_details.owner.user_id, self.user_id)

    def test_participant_details_api_call(self):
        tool = self._create_tool(api_call = 5)
        record = self.service.track_api_call(
            tool = tool,
            tool_purpose = ToolType.api_twitter,
            runtime_seconds = 1,
            payer_id = self.user_id,
            uses_credits = True,
        )
        self.assertIsNotNone(record.participant_details)
        self.assertIsNotNone(record.participant_details.payer)
        self.assertEqual(record.participant_details.payer.user_id, self.user_id)
        self.assertIsNotNone(record.participant_details.owner)
        self.assertEqual(record.participant_details.owner.user_id, self.user_id)

    def _create_search_tool(self, web_search_query: float = 1.4) -> ExternalTool:
        provider = ExternalToolProvider(
            id = "test-provider",
            name = "Test Provider",
            token_management_url = "https://test.com",
            token_format = "test",
            tools = [],
        )
        return ExternalTool(
            id = "test-search-tool",
            name = "Test Search Tool",
            provider = provider,
            types = [ToolType.search],
            cost_estimate = CostEstimate(
                input_1m_tokens = 100,
                output_1m_tokens = 200,
                web_search_query = web_search_query,
            ),
        )

    def test_track_web_search_query_emits_correct_record_count(self):
        tool = self._create_search_tool()
        records = self.service.track_web_search_query(
            tool = tool,
            tool_purpose = ToolType.search,
            runtime_seconds = 2.0,
            payer_id = self.payer_id,
            uses_credits = False,
            query_count = 3,
        )
        self.assertEqual(len(records), 3)
        self.assertEqual(self.mock_di.usage_record_repo.create.call_count, 3)

    def test_track_web_search_query_fee_placement(self):
        tool = self._create_search_tool(web_search_query = 1.4)
        records = self.service.track_web_search_query(
            tool = tool,
            tool_purpose = ToolType.search,
            runtime_seconds = 1.0,
            payer_id = self.payer_id,
            uses_credits = False,
            query_count = 2,
        )
        for record in records:
            self.assertAlmostEqual(record.api_call_cost_credits, 1.4, places = 5)
            self.assertEqual(record.model_cost_credits, 0.0)
            self.assertEqual(record.maintenance_fee_credits, 0.0)
            self.assertAlmostEqual(record.total_cost_credits, 1.4, places = 5)

    def test_track_web_search_query_zero_count_returns_empty(self):
        tool = self._create_search_tool()
        records = self.service.track_web_search_query(
            tool = tool,
            tool_purpose = ToolType.search,
            runtime_seconds = 1.0,
            payer_id = self.payer_id,
            uses_credits = False,
            query_count = 0,
        )
        self.assertEqual(records, [])
        self.mock_di.usage_record_repo.create.assert_not_called()

    def test_track_web_search_query_payer_id_stored(self):
        tool = self._create_search_tool()
        records = self.service.track_web_search_query(
            tool = tool,
            tool_purpose = ToolType.search,
            runtime_seconds = 1.0,
            payer_id = self.payer_id,
            uses_credits = True,
            query_count = 1,
        )
        self.assertEqual(records[0].payer_id, self.payer_id)
        self.assertTrue(records[0].uses_credits)
