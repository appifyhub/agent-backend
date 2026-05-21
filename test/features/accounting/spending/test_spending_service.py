import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import UUID

from pydantic import SecretStr

from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.accounting.spending.spending_service import SpendingService
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from util.errors import NotFoundError, ValidationError


def _make_user(user_id: int = 1, credit_balance: float = 100.0) -> User:
    return User(
        id = UUID(int = user_id),
        full_name = "Test User",
        telegram_user_id = user_id,
        telegram_chat_id = str(user_id),
        group = UserDB.Group.standard,
        created_at = datetime.now().date(),
        credit_balance = credit_balance,
    )


def _make_configured_tool(payer_id: UUID, uses_credits: bool = True) -> ConfiguredTool:
    provider = ExternalToolProvider(
        id = "test-provider",
        name = "Test Provider",
        token_management_url = "https://test.com",
        token_format = "test",
        tools = [],
    )
    tool = ExternalTool(
        id = "test-tool",
        name = "Test Tool",
        provider = provider,
        types = [ToolType.chat],
        cost_estimate = CostEstimate(
            input_1m_tokens = 100,
            output_1m_tokens = 200,
        ),
    )
    return ConfiguredTool(
        definition = tool,
        token = SecretStr("test-token"),
        purpose = ToolType.chat,
        payer_id = payer_id,
        uses_credits = uses_credits,
    )


class SpendingServiceValidatePreFlightTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.service = SpendingService(self.mock_di)
        self.payer_id = UUID(int = 1)

    def test_does_nothing_when_not_using_credits(self):
        tool = _make_configured_tool(self.payer_id, uses_credits = False)

        self.service.validate_pre_flight(tool, input_text = "a" * 4000)

        self.mock_di.user_crud.get.assert_not_called()

    def test_passes_when_balance_is_sufficient(self):
        user = _make_user(credit_balance = 100.0)
        user_db = UserDB(**user.model_dump())
        self.mock_di.user_crud.get.return_value = user_db
        tool = _make_configured_tool(self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            self.service.validate_pre_flight(tool, max_output_tokens = 0)

        self.mock_di.user_crud.get.assert_called_once_with(self.payer_id)

    def test_raises_when_user_not_found(self):
        self.mock_di.user_crud.get.return_value = None
        tool = _make_configured_tool(self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            with self.assertRaises(NotFoundError):
                self.service.validate_pre_flight(tool)

    def test_raises_when_balance_is_negative(self):
        user = _make_user(credit_balance = -10.0)
        user_db = UserDB(**user.model_dump())
        self.mock_di.user_crud.get.return_value = user_db
        tool = _make_configured_tool(self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_pre_flight(tool)

        self.assertIn("Insufficient credits", str(ctx.exception))

    def test_raises_when_balance_is_insufficient(self):
        user = _make_user(credit_balance = 0.5)
        user_db = UserDB(**user.model_dump())
        self.mock_di.user_crud.get.return_value = user_db
        tool = _make_configured_tool(self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 5.0
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_pre_flight(tool)

        self.assertIn("Insufficient credits", str(ctx.exception))


class SpendingServiceDeductTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.service = SpendingService(self.mock_di)
        self.payer_id = UUID(int = 1)

    def test_does_nothing_when_not_using_credits(self):
        tool = _make_configured_tool(self.payer_id, uses_credits = False)

        self.service.deduct(tool, 10.0)

        self.mock_di.user_crud.update_locked.assert_not_called()

    def test_calls_update_locked_when_using_credits(self):
        tool = _make_configured_tool(self.payer_id, uses_credits = True)

        self.service.deduct(tool, 10.0)

        self.mock_di.user_crud.update_locked.assert_called_once()
        call_args = self.mock_di.user_crud.update_locked.call_args
        self.assertEqual(call_args.args[0], self.payer_id)

    def test_deduct_reduces_balance(self):
        tool = _make_configured_tool(self.payer_id, uses_credits = True)
        user = _make_user(credit_balance = 50.0)

        captured_apply = None

        def capture_update_locked(user_id, apply_fn):
            nonlocal captured_apply
            captured_apply = apply_fn

        self.mock_di.user_crud.update_locked.side_effect = capture_update_locked

        self.service.deduct(tool, 10.0)

        self.assertIsNotNone(captured_apply)
        captured_apply(user)
        self.assertAlmostEqual(user.credit_balance, 40.0, places = 5)

    def test_deduct_allows_negative_balance(self):
        tool = _make_configured_tool(self.payer_id, uses_credits = True)
        user = _make_user(credit_balance = 5.0)

        captured_apply = None

        def capture_update_locked(user_id, apply_fn):
            nonlocal captured_apply
            captured_apply = apply_fn

        self.mock_di.user_crud.update_locked.side_effect = capture_update_locked

        self.service.deduct(tool, 50.0)

        self.assertIsNotNone(captured_apply)
        captured_apply(user)
        self.assertAlmostEqual(user.credit_balance, -45.0, places = 5)
