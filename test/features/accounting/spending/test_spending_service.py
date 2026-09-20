import unittest
from unittest.mock import Mock, patch
from uuid import UUID

import stubs

from di.di import DI
from features.accounting.spending.spending_service import SpendingService
from util.errors import NotFoundError, ValidationError


class SpendingServiceValidatePreFlightTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.service = SpendingService(self.mock_di)
        self.payer_id = UUID(int = 1)

    def test_does_nothing_when_not_using_credits(self):
        tool = stubs.domain.configured_tool(uses_credits = False)

        self.service.validate_pre_flight(tool, input_text = "a" * 4000)

        self.mock_di.user_repo.get.assert_not_called()

    def test_passes_when_balance_is_sufficient(self):
        self.mock_di.user_repo.get.return_value = stubs.domain.user()
        tool = stubs.domain.configured_tool(payer_id = self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            self.service.validate_pre_flight(tool, max_output_tokens = 0)

        self.mock_di.user_repo.get.assert_called_once_with(self.payer_id)

    def test_raises_when_user_not_found(self):
        self.mock_di.user_repo.get.return_value = None
        tool = stubs.domain.configured_tool(payer_id = self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            with self.assertRaises(NotFoundError):
                self.service.validate_pre_flight(tool)

    def test_raises_when_balance_is_negative(self):
        self.mock_di.user_repo.get.return_value = stubs.domain.user(credit_balance = -10.0)
        tool = stubs.domain.configured_tool(payer_id = self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_pre_flight(tool)

        self.assertIn("Insufficient credits", str(ctx.exception))

    def test_raises_when_balance_is_insufficient(self):
        self.mock_di.user_repo.get.return_value = stubs.domain.user(credit_balance = 0.5)
        tool = stubs.domain.configured_tool(payer_id = self.payer_id, uses_credits = True)

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 5.0
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_pre_flight(tool)

        self.assertIn("Insufficient credits", str(ctx.exception))

    def test_uses_video_size_and_duration_in_cost_estimate(self):
        self.mock_di.user_repo.get.return_value = stubs.domain.user(credit_balance = 15.5)
        tool = stubs.domain.configured_tool(
            payer_id = self.payer_id,
            uses_credits = True,
            definition = stubs.domain.external_tool(
                cost_estimate = stubs.domain.cost_estimate(
                    output_video_2k_second = 3,
                    api_call = None,
                    web_search_query = None,
                ),
            ),
        )

        with patch("features.accounting.spending.spending_service.config") as mock_config:
            mock_config.usage_maintenance_fee_credits = 1.0
            with self.assertRaises(ValidationError) as ctx:
                self.service.validate_pre_flight(
                    tool,
                    input_text = "",
                    max_output_tokens = 0,
                    output_video_size = "2K",
                    output_video_duration_seconds = 5,
                )

        self.assertIn("minimum required 16.0", str(ctx.exception))


class SpendingServiceDeductTest(unittest.TestCase):

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.service = SpendingService(self.mock_di)
        self.payer_id = UUID(int = 1)

    def test_does_nothing_when_not_using_credits(self):
        tool = stubs.domain.configured_tool(uses_credits = False)

        self.service.deduct(tool, 10.0)

        self.mock_di.user_repo.update_locked.assert_not_called()

    def test_calls_update_locked_when_using_credits(self):
        tool = stubs.domain.configured_tool(payer_id = self.payer_id, uses_credits = True)

        self.service.deduct(tool, 10.0)

        self.mock_di.user_repo.update_locked.assert_called_once()
        call_args = self.mock_di.user_repo.update_locked.call_args
        self.assertEqual(call_args.args[0], self.payer_id)

    def test_deduct_reduces_balance(self):
        tool = stubs.domain.configured_tool(uses_credits = True)
        user = stubs.domain.user(credit_balance = 50.0)

        captured_apply = None

        def capture_update_locked(user_id, apply_fn):
            nonlocal captured_apply
            captured_apply = apply_fn

        self.mock_di.user_repo.update_locked.side_effect = capture_update_locked

        self.service.deduct(tool, 10.0)

        self.assertIsNotNone(captured_apply)
        updated_user = captured_apply(user)
        self.assertAlmostEqual(updated_user.credit_balance, 40.0, places = 5)

    def test_deduct_allows_negative_balance(self):
        tool = stubs.domain.configured_tool(uses_credits = True)
        user = stubs.domain.user(credit_balance = 5.0)

        captured_apply = None

        def capture_update_locked(user_id, apply_fn):
            nonlocal captured_apply
            captured_apply = apply_fn

        self.mock_di.user_repo.update_locked.side_effect = capture_update_locked

        self.service.deduct(tool, 50.0)

        self.assertIsNotNone(captured_apply)
        updated_user = captured_apply(user)
        self.assertAlmostEqual(updated_user.credit_balance, -45.0, places = 5)
