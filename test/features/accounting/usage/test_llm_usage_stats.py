import unittest
from unittest.mock import Mock

import stubs
from langchain_core.messages import AIMessage

from features.accounting.usage.llm_usage_stats import LLMUsageStats


class LLMUsageStatsTest(unittest.TestCase):

    def test_from_usage_metadata_with_all_fields(self):
        metadata = {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 300)
        self.assertIsNone(stats.search_tokens)

    def test_from_usage_metadata_with_alternative_field_names(self):
        metadata = {
            "prompt_tokens": 150,
            "completion_tokens": 250,
            "total_token_count": 400,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertEqual(stats.input_tokens, 150)
        self.assertEqual(stats.output_tokens, 250)
        self.assertEqual(stats.total_tokens, 400)

    def test_from_usage_metadata_calculates_total_when_missing(self):
        metadata = {
            "input_tokens": 100,
            "output_tokens": 200,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertEqual(stats.total_tokens, 300)

    def test_from_usage_metadata_with_duration(self):
        metadata = {
            "seconds": 7.5,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertEqual(stats.remote_runtime_seconds, 7.5)
        self.assertIsNone(stats.total_tokens)

    def test_from_usage_metadata_with_alternative_duration(self):
        metadata = {
            "duration": 12.3,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertEqual(stats.remote_runtime_seconds, 12.3)

    def test_from_usage_metadata_with_object(self):
        class UsageObj:

            def __init__(self, seconds: float):
                self.seconds = seconds

        usage_obj = UsageObj(seconds = 10.0)
        stats = LLMUsageStats.from_usage_metadata(usage_obj)

        self.assertEqual(stats.remote_runtime_seconds, 10.0)

    def test_from_usage_metadata_with_empty_dict(self):
        stats = LLMUsageStats.from_usage_metadata({})

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)
        self.assertIsNone(stats.search_tokens)

    def test_from_usage_metadata_total_none_when_zero(self):
        metadata = {
            "input_tokens": 0,
            "output_tokens": 0,
        }
        stats = LLMUsageStats.from_usage_metadata(metadata)

        self.assertIsNone(stats.total_tokens)

    def test_decorate_with_perplexity_stats_with_reasoning_and_citation(self):
        base_stats = stubs.domain.llm_usage_stats(
            input_tokens = 100,
            output_tokens = 200,
            total_tokens = 300,
            search_tokens = None,
            remote_runtime_seconds = None,
        )
        usage_metadata = {
            "output_token_details": {
                "reasoning": 50,
                "citation_tokens": 30,
            },
        }

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertEqual(result.input_tokens, 100)
        self.assertEqual(result.output_tokens, 200)
        self.assertEqual(result.search_tokens, 80)
        self.assertEqual(result.total_tokens, 380)

    def test_decorate_with_perplexity_stats_with_reasoning_only(self):
        base_stats = stubs.domain.llm_usage_stats(
            total_tokens = 300,
            search_tokens = None,
            remote_runtime_seconds = None,
        )
        usage_metadata = {
            "output_token_details": {
                "reasoning": 50,
            },
        }

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertEqual(result.search_tokens, 50)
        self.assertEqual(result.total_tokens, 350)

    def test_decorate_with_perplexity_stats_with_citation_only(self):
        base_stats = stubs.domain.llm_usage_stats(
            total_tokens = 300,
            search_tokens = None,
            remote_runtime_seconds = None,
        )
        usage_metadata = {
            "output_token_details": {
                "citation_tokens": 30,
            },
        }

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertEqual(result.search_tokens, 30)
        self.assertEqual(result.total_tokens, 330)

    def test_decorate_with_perplexity_stats_without_perplexity_data(self):
        base_stats = stubs.domain.llm_usage_stats(
            input_tokens = 100,
            output_tokens = 200,
            search_tokens = None,
            total_tokens = 300,
            remote_runtime_seconds = None,
        )
        usage_metadata = {}

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertEqual(result.input_tokens, 100)
        self.assertEqual(result.output_tokens, 200)
        self.assertEqual(result.total_tokens, 300)
        self.assertIsNone(result.search_tokens)

    def test_decorate_with_perplexity_stats_with_none_base_total(self):
        base_stats = stubs.domain.llm_usage_stats(
            total_tokens = None,
            input_tokens = None,
            output_tokens = None,
            search_tokens = None,
            remote_runtime_seconds = None,
        )
        usage_metadata = {
            "output_token_details": {
                "reasoning": 50,
                "citation_tokens": 30,
            },
        }

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertEqual(result.search_tokens, 80)
        self.assertEqual(result.total_tokens, 80)

    def test_decorate_with_perplexity_stats_ignores_non_int_values(self):
        base_stats = stubs.domain.llm_usage_stats(
            total_tokens = 300,
            search_tokens = None,
            remote_runtime_seconds = None,
        )
        usage_metadata = {
            "output_token_details": {
                "reasoning": "not_an_int",
                "citation_tokens": None,
            },
        }

        result = LLMUsageStats.decorate_with_perplexity_stats(base_stats, usage_metadata)

        self.assertIsNone(result.search_tokens)
        self.assertEqual(result.total_tokens, 300)

    def test_from_response_with_response_metadata(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
            },
        }

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 300)

    def test_from_response_with_usage_metadata_attribute(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {}
        response.usage_metadata = {
            "input_tokens": 150,
            "output_tokens": 250,
        }

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 150)
        self.assertEqual(stats.output_tokens, 250)

    def test_from_response_with_perplexity_tokens(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
            },
        }
        response.usage_metadata = None

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.search_tokens, None)
        self.assertEqual(stats.total_tokens, 300)

    def test_from_response_with_fallback_to_metadata_fields(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
        }
        response.usage_metadata = None

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 300)

    def test_from_response_with_x_ai_chat_token_usage(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {
            "token_usage": {
                "completion_tokens": 8,
                "prompt_tokens": 176,
                "total_tokens": 184,
                "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 0,
                    "rejected_prediction_tokens": 0,
                },
                "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 161,
                    "text_tokens": 176,
                    "image_tokens": 0,
                },
                "num_sources_used": 0,
                "cost_in_usd_ticks": 150500,
            },
            "model_provider": "xai",
            "model_name": "grok-4-1-fast-non-reasoning",
            "finish_reason": "stop",
        }
        response.usage_metadata = None

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 176)
        self.assertEqual(stats.output_tokens, 8)
        self.assertEqual(stats.total_tokens, 184)

    def test_from_response_with_perplexity_tokens_in_usage(self):
        response = Mock(spec = AIMessage)
        response.response_metadata = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
                "output_token_details": {
                    "reasoning": 50,
                    "citation_tokens": 30,
                },
            },
        }
        response.usage_metadata = None

        stats = LLMUsageStats.from_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.search_tokens, 80)
        self.assertEqual(stats.total_tokens, 380)
