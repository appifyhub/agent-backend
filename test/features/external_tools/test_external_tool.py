import unittest

from features.external_tools.external_tool import CostEstimate, ToolType


class ExternalToolTest(unittest.TestCase):

    def test_returns_zero_for_empty_estimate(self):
        estimate = CostEstimate()

        result = estimate.get_minimum_for()

        self.assertEqual(result, 0.0)

    def test_counts_input_tokens_from_text(self):
        # 4000 chars → 1000 tokens; (1000 / 1_000_000) * 1000 = 1.0
        estimate = CostEstimate(input_1m_tokens = 1000)

        result = estimate.get_minimum_for(input_text = "a" * 4000)

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_counts_output_tokens(self):
        # (1000 / 1_000_000) * 1000 = 1.0
        estimate = CostEstimate(output_1m_tokens = 1000)

        result = estimate.get_minimum_for(input_text = "", max_output_tokens = 1000)

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_default_max_output_tokens_is_1000(self):
        # default max_output_tokens=1000; (1000 / 1_000_000) * 1000 = 1.0
        estimate = CostEstimate(output_1m_tokens = 1000)

        result = estimate.get_minimum_for()

        self.assertAlmostEqual(result, 1.0, places = 5)

    def test_counts_search_tokens(self):
        # (1000 / 1_000_000) * 1000 = 1.0
        estimate = CostEstimate(search_1m_tokens = 1000)

        result = estimate.get_minimum_for(search_tokens = 1000)

        self.assertAlmostEqual(result, 1.0, places = 3)

    def test_counts_runtime_seconds(self):
        estimate = CostEstimate(second_of_runtime = 2.5)

        result = estimate.get_minimum_for(runtime_seconds = 4.0)

        self.assertAlmostEqual(result, 10.0, places = 3)

    def test_adds_api_call_cost(self):
        estimate = CostEstimate(api_call = 5)

        result = estimate.get_minimum_for()

        self.assertEqual(result, 5.0)

    def test_adds_web_search_query_cost(self):
        estimate = CostEstimate(web_search_query = 1.4)

        result = estimate.get_minimum_for()

        self.assertAlmostEqual(result, 1.4, places = 5)

    def test_adds_input_image_costs_by_size(self):
        estimate = CostEstimate(
            input_image_1k = 1, input_image_2k = 2, input_image_4k = 4, input_image_8k = 8, input_image_12k = 12,
        )

        result = estimate.get_minimum_for(input_image_sizes = ["1k", "4k", "12k"])

        self.assertEqual(result, 17.0)

    def test_adds_output_image_costs_by_size(self):
        estimate = CostEstimate(output_image_1k = 3, output_image_2k = 6, output_image_4k = 12)

        result = estimate.get_minimum_for(output_image_sizes = ["2k", "4k"])

        self.assertEqual(result, 18.0)

    def test_normalizes_image_size_strings(self):
        estimate = CostEstimate(input_image_1k = 1, input_image_2k = 2, output_image_2k = 6)

        result = estimate.get_minimum_for(
            input_image_sizes = ["2mp", "2 mb"],
            output_image_sizes = ["2m"],
        )

        self.assertEqual(result, 10.0)

    def test_unknown_image_size_falls_back_to_1k(self):
        estimate = CostEstimate(input_image_1k = 10)

        result = estimate.get_minimum_for(input_image_sizes = ["99k"])

        self.assertEqual(result, 10.0)

    def test_empty_input_text_skips_token_cost(self):
        estimate = CostEstimate(input_1m_tokens = 1_000_000)

        result = estimate.get_minimum_for(input_text = "")

        self.assertEqual(result, 0.0)

    def test_combines_all_costs(self):
        # input: 4000 chars → 1000 tokens; (1000/1M)*1000 = 1.0
        # output: (1000/1M)*1000 = 1.0
        # api_call: 10.0
        # web_search_query: 1.4
        # input_image_1k: 5.0
        # output_image_2k: 3.0
        # total: 21.4
        estimate = CostEstimate(
            input_1m_tokens = 1000,
            output_1m_tokens = 1000,
            api_call = 10,
            web_search_query = 1.4,
            input_image_1k = 5,
            output_image_2k = 3,
        )

        result = estimate.get_minimum_for(
            input_text = "a" * 4000,
            max_output_tokens = 1000,
            input_image_sizes = ["1k"],
            output_image_sizes = ["2k"],
        )

        self.assertAlmostEqual(result, 21.4, places = 3)

    def test_temperature_percent_for_llm_types(self):
        self.assertEqual(ToolType.chat.temperature_percent, 0.25)
        self.assertEqual(ToolType.reasoning.temperature_percent, 0.25)
        self.assertEqual(ToolType.copywriting.temperature_percent, 0.4)
        self.assertEqual(ToolType.vision.temperature_percent, 0.25)
        self.assertEqual(ToolType.search.temperature_percent, 0.35)

    def test_temperature_percent_zero_for_non_llm_types(self):
        non_llm = [
            ToolType.hearing,
            ToolType.images_gen,
            ToolType.images_edit,
            ToolType.embedding,
            ToolType.api_fiat_exchange,
            ToolType.api_crypto_exchange,
            ToolType.api_stock_quote,
            ToolType.api_twitter,
            ToolType.deprecated,
        ]
        for tool_type in non_llm:
            with self.subTest(tool_type = tool_type):
                self.assertEqual(tool_type.temperature_percent, 0.0)
