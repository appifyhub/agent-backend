from dataclasses import replace
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_chat_model import FakeChatModel
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.chat_model_usage_tracking_decorator import ChatModelUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool_library import GPT_5_5
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class ChatModelUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    model: FakeChatModel
    decorator: ChatModelUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = GPT_5_5.id),
            uses_credits = True,
        )
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool, max_tokens = 4096))
        self.decorator = self.di.chat_langchain_model(self.tool)
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_model_and_bound_runnable_track_usage_and_deduct_credits(self):
        for subject in (self.decorator, self.decorator.bind_tools([])):
            with self.subTest(subject = type(subject).__name__):
                response = stubs.external.ai_message(response_metadata = {
                    "usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
                })
                self.model.responses.append(response)
                messages = [stubs.external.human_message()]

                result = subject.invoke(messages)

                self.assertEqual(result, response)
                self.assertEqual(self.model.prompts[-1], messages)
                record = self.di.usage_record_repo.get_by_user(self.user.id)[0]
                self.assertEqual(record.tool.id, self.tool.definition.id)
                self.assertEqual(record.tool_purpose, self.tool.purpose)
                self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (100, 200, 300))
                self.assertTrue(record.uses_credits)
                self.assertFalse(record.is_failed)
        records = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(len(records), 2)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - sum(record.total_cost_credits for record in records),
        )

    def test_model_and_bound_runnable_measure_runtime(self):
        for subject in (self.decorator, self.decorator.bind_tools([])):
            with self.subTest(subject = type(subject).__name__):
                self.model.responses.append(stubs.external.ai_message())
                # control only the system clock; model invocation and accounting remain real
                with patch(
                    "features.accounting.usage.decorators.chat_model_usage_tracking_decorator.time",
                    side_effect = [10, 10.25],
                ):
                    subject.invoke([stubs.external.human_message()])
                record = self.di.usage_record_repo.get_by_user(self.user.id)[0]
                self.assertEqual(record.runtime_seconds, 0.25)

    def test_invoke_passes_arguments_correctly(self):
        self.model.responses.append(stubs.external.ai_message())
        messages = [stubs.external.human_message()]

        self.decorator.invoke(messages, {"tags": ["test"]}, stream = False)

        self.assertEqual(self.model.prompts, [messages])
        self.assertEqual(self.model.invocations, [({"tags": ["test"]}, {"stream": False})])

    def test_generate_delegates_to_wrapped_model_without_tracking(self):
        response = stubs.external.ai_message()
        self.model.responses.append(response)

        result = self.decorator._generate([stubs.external.human_message()])

        self.assertEqual(result.generations[0].message, response)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])

    def test_llm_type_delegates_to_wrapped_model(self):
        self.assertEqual(self.decorator._llm_type, self.model._llm_type)

    def test_model_and_bound_runnable_reject_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))
        for subject in (self.decorator, self.decorator.bind_tools([])):
            with self.subTest(subject = type(subject).__name__), self.assertRaises(ValidationError) as raised:
                subject.invoke([stubs.external.human_message()])
            self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_model_and_bound_runnable_failures_track_without_deduction(self):
        for subject in (self.decorator, self.decorator.bind_tools([])):
            with self.subTest(subject = type(subject).__name__):
                error = ExternalServiceError("API error", UNEXPECTED_ERROR)
                self.model.responses.append(error)
                with self.assertRaises(ExternalServiceError) as raised:
                    subject.invoke([stubs.external.human_message()])
                self.assertIs(raised.exception, error)
        records = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.is_failed for record in records))
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)
