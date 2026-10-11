import unittest

import stubs


class ExternalToolTest(unittest.TestCase):

    def test_returns_zero_for_empty_estimate(self):
        estimate = stubs.domain.cost_estimate(
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertEqual(result, 0.0)

    def test_counts_input_tokens_from_text(self):
        # 4000 chars → 1000 tokens; (1000 / 1_000_000) * 1000 = 1.0
        estimate = stubs.domain.cost_estimate(
            input_1m_tokens = 1000,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "a" * 4000,
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_counts_output_tokens(self):
        # (1000 / 1_000_000) * 1000 = 1.0
        estimate = stubs.domain.cost_estimate(
            output_1m_tokens = 1000,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 1000,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_counts_search_tokens(self):
        # (1000 / 1_000_000) * 1000 = 1.0
        estimate = stubs.domain.cost_estimate(
            search_1m_tokens = 1000,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 1000,
            runtime_seconds = 0,
        )

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_counts_runtime_seconds(self):
        estimate = stubs.domain.cost_estimate(
            second_of_runtime = 2.5,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 4.0,
        )

        self.assertAlmostEqual(result, 10.0, places = 3)

    def test_adds_api_call_cost(self):
        estimate = stubs.domain.cost_estimate(
            api_call = 5,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertEqual(result, 5.0)

    def test_adds_web_search_query_cost(self):
        estimate = stubs.domain.cost_estimate(
            web_search_query = 1.4,
            api_call = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertAlmostEqual(result, 1.4, places = 5)

    def test_adds_input_image_costs_by_size(self):
        estimate = stubs.domain.cost_estimate(
            input_image_1k = 1,
            input_image_2k = 2,
            input_image_4k = 4,
            input_image_8k = 8,
            input_image_12k = 12,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
            input_image_sizes = ["1k", "4k", "12k"],
        )

        self.assertEqual(result, 17.0)

    def test_adds_output_image_costs_by_size(self):
        estimate = stubs.domain.cost_estimate(
            output_image_1k = 3,
            output_image_2k = 6,
            output_image_4k = 12,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
            output_image_sizes = ["2k", "4k"],
        )

        self.assertEqual(result, 18.0)

    def test_adds_output_video_cost_by_size_and_duration(self):
        estimate = stubs.domain.cost_estimate(
            output_video_1k_second = 2,
            output_video_2k_second = 4,
            output_video_4k_second = 8,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

        self.assertEqual(result, 20.0)

    def test_normalizes_image_size_strings(self):
        estimate = stubs.domain.cost_estimate(
            input_image_1k = 1,
            input_image_2k = 2,
            output_image_2k = 6,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
            input_image_sizes = ["2mp", "2 mb"],
            output_image_sizes = ["2m"],
        )

        self.assertEqual(result, 10.0)

    def test_unknown_image_size_falls_back_to_1k(self):
        estimate = stubs.domain.cost_estimate(
            input_image_1k = 10,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
            input_image_sizes = ["99k"],
        )

        self.assertEqual(result, 10.0)

    def test_empty_input_text_skips_token_cost(self):
        estimate = stubs.domain.cost_estimate(
            input_1m_tokens = 1_000_000,
            api_call = None,
            web_search_query = None,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            search_tokens = 0,
            runtime_seconds = 0,
        )

        self.assertEqual(result, 0.0)

    def test_combines_all_costs(self):
        # input: 4000 chars → 1000 tokens; (1000/1M)*1000 = 1.0
        # output: (1000/1M)*1000 = 1.0
        # api_call: 10.0
        # web_search_query: 1.4
        # input_image_1k: 5.0
        # output_image_2k: 3.0
        # total: 21.4
        estimate = stubs.domain.cost_estimate(
            input_1m_tokens = 1000,
            output_1m_tokens = 1000,
            input_image_1k = 5,
            output_image_2k = 3,
            api_call = 10,
            web_search_query = 1.4,
        )

        result = estimate.get_minimum_for(
            input_text = "a" * 4000,
            max_output_tokens = 1000,
            input_image_sizes = ["1k"],
            search_tokens = 0,
            runtime_seconds = 0,
            output_image_sizes = ["2k"],
        )

        self.assertAlmostEqual(result, 21.4, places = 3)
