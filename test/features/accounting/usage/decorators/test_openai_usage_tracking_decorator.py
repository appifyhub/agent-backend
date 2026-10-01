from dataclasses import replace
from io import BytesIO
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_openai_client import FakeOpenAIClient
from util.di_utils import di_for_tests

from di.di import DI
from features.accounting.usage.decorators.openai_usage_tracking_decorator import OpenAIUsageTrackingDecorator
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import WHISPER_1
from features.users.user import User
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, UNEXPECTED_ERROR
from util.errors import ExternalServiceError, ValidationError


class OpenAIUsageTrackingDecoratorTest(TestCase):

    di: DI
    user: User
    tool: ConfiguredTool
    client: FakeOpenAIClient
    decorator: OpenAIUsageTrackingDecorator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.di.inject_invoker(self.user)
        self.tool = stubs.domain.configured_tool(
            definition = stubs.domain.external_tool(id = WHISPER_1.id),
            purpose = ToolType.hearing,
            uses_credits = True,
        )
        self.client = cast(FakeOpenAIClient, self.di.base_open_ai_client(self.tool))
        self.decorator = self.di.open_ai_client(self.tool)
        self.addCleanup(setattr, config, "usage_maintenance_fee_credits", config.usage_maintenance_fee_credits)
        config.usage_maintenance_fee_credits = 1.0

    def test_audio_transcriptions_tracks_usage_and_deducts_credits(self):
        response = stubs.external.openai_transcription(usage = {
            "type": "tokens", "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
        })
        self.client.audio.transcriptions.responses.append(response)

        result = self.decorator.audio.transcriptions.create(model = "whisper-1", file = BytesIO(b"audio"))

        self.assertEqual(result, response)
        self.assertEqual(self.client.audio.transcriptions.recordings, [b"audio"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.tool.id, self.tool.definition.id)
        self.assertEqual(record.tool_purpose, ToolType.hearing)
        self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (100, 50, 150))
        self.assertTrue(record.uses_credits)
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_audio_transcriptions_measures_runtime(self):
        self.client.audio.transcriptions.responses.append(stubs.external.openai_transcription())
        # the system clock makes elapsed time deterministic
        with patch("features.accounting.usage.decorators.openai_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            self.decorator.audio.transcriptions.create(model = "whisper-1", file = BytesIO(b"audio"))

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_embeddings_tracks_usage_and_deducts_credits(self):
        response = stubs.external.openai_embedding_response(usage = {"prompt_tokens": 50, "total_tokens": 50})
        self.client.embeddings.responses.append(response)

        result = self.decorator.embeddings.create(model = "text-embedding-3-small", input = "test")

        self.assertEqual(result, response)
        self.assertEqual(self.client.embeddings.inputs, ["test"])
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual((record.input_tokens, record.total_tokens), (50, 50))
        self.assertFalse(record.is_failed)
        self.assertAlmostEqual(
            self.di.user_repo.get(self.user.id).credit_balance,
            self.user.credit_balance - record.total_cost_credits,
        )

    def test_embeddings_measures_runtime(self):
        self.client.embeddings.responses.append(stubs.external.openai_embedding_response())
        # the system clock makes elapsed time deterministic
        with patch("features.accounting.usage.decorators.openai_usage_tracking_decorator.time", side_effect = [10, 10.25]):
            self.decorator.embeddings.create(model = "text-embedding-3-small", input = "test")

        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertEqual(record.runtime_seconds, 0.25)

    def test_delegates_other_attributes(self):
        self.assertEqual(self.decorator.api_key, self.client.api_key)

    def test_audio_transcriptions_rejects_insufficient_balance_before_request(self):
        user = self.di.user_repo.save(replace(self.user, credit_balance = 0))

        with self.assertRaises(ValidationError) as raised:
            self.decorator.audio.transcriptions.create(model = "whisper-1", file = BytesIO(b"audio"))

        self.assertEqual(raised.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.client.audio.transcriptions.recordings, [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.user.id), [])
        self.assertEqual(self.di.user_repo.get(self.user.id), user)

    def test_audio_transcriptions_failure_tracks_without_deduction(self):
        error = ExternalServiceError("API error", UNEXPECTED_ERROR)
        self.client.audio.transcriptions.responses.append(error)

        with self.assertRaises(ExternalServiceError) as raised:
            self.decorator.audio.transcriptions.create(model = "whisper-1", file = BytesIO(b"audio"))

        self.assertIs(raised.exception, error)
        record, = self.di.usage_record_repo.get_by_user(self.user.id)
        self.assertTrue(record.is_failed)
        self.assertEqual(self.di.user_repo.get(self.user.id), self.user)
