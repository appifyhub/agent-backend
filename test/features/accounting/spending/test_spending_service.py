from dataclasses import replace
from unittest import TestCase

import stubs
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.spending.spending_service import SpendingService
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, USER_NOT_FOUND
from util.errors import NotFoundError, ValidationError


class SpendingServiceValidatePreFlightTest(TestCase):

    di: DI
    service: SpendingService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.spending_service
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_does_nothing_when_not_using_credits(self):
        tool = stubs.domain.configured_tool()

        self.assertIsNone(self.service.validate_pre_flight(tool, input_text = "a" * 4000))

    def test_passes_when_balance_is_sufficient(self):
        user = self.di.user_repo.save(stubs.domain.user())
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.assertIsNone(self.service.validate_pre_flight(tool, max_output_tokens = 0))

        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_raises_when_user_not_found(self):
        tool = stubs.domain.configured_tool(uses_credits = True)

        with self.assertRaises(NotFoundError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, USER_NOT_FOUND)

    def test_raises_when_balance_is_negative(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = -10.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("Insufficient credits", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_raises_when_balance_is_insufficient(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 0.5))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(tool)

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("Insufficient credits", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_uses_video_size_and_duration_in_cost_estimate(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 15.5))
        tool = stubs.domain.configured_tool(
            uses_credits = True,
            payer_id = user.id,
            definition = stubs.domain.external_tool(
                cost_estimate = stubs.domain.cost_estimate(
                    output_video_2k_second = 3,
                    api_call = None,
                    web_search_query = None,
                ),
            ),
        )

        with self.assertRaises(ValidationError) as context:
            self.service.validate_pre_flight(
                tool,
                input_text = "",
                max_output_tokens = 0,
                output_video_size = "2K",
                output_video_duration_seconds = 5,
            )

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertIn("minimum required 16.0", str(context.exception))
        self.assertEqual(self.di.user_repo.get(user.id), user)


class SpendingServiceDeductTest(TestCase):

    di: DI
    service: SpendingService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.spending_service

    def test_does_nothing_when_not_using_credits(self):
        user = self.di.user_repo.save(stubs.domain.user())
        tool = stubs.domain.configured_tool(payer_id = user.id)

        self.service.deduct(tool, 10.0)

        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_deduct_reduces_balance(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 50.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.service.deduct(tool, 10.0)

        self.assertEqual(self.di.user_repo.get(user.id), replace(user, credit_balance = 40.0))

    def test_deduct_allows_negative_balance(self):
        user = self.di.user_repo.save(stubs.domain.user(credit_balance = 5.0))
        tool = stubs.domain.configured_tool(uses_credits = True, payer_id = user.id)

        self.service.deduct(tool, 50.0)

        self.assertEqual(self.di.user_repo.get(user.id), replace(user, credit_balance = -45.0))
