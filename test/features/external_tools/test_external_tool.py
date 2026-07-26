import unittest

from features.external_tools.external_tool import CostEstimate, ToolType
from features.external_tools.external_tool_library import (
    ALL_EXTERNAL_TOOLS,
    CLAUDE_5_OPUS,
    GPT_5_6_LUNA,
    GPT_5_6_SOL,
    GPT_5_6_TERRA,
    VIDEO_GEN_P_VIDEO,
    VIDEO_GEN_RAY_3_2,
    VIDEO_GEN_SEEDANCE_2_0,
    VIDEO_GEN_SEEDANCE_2_0_FAST,
    VIDEO_GEN_VEO_3_1,
    VIDEO_GEN_VEO_3_1_FAST,
)
from features.external_tools.external_tool_provider_library import REPLICATE


class ExternalToolTest(unittest.TestCase):

    def test_new_text_models_have_expected_ids_types_and_costs(self):
        expected_types = [ToolType.chat, ToolType.reasoning, ToolType.copywriting, ToolType.vision]
        expected_models = (
            (GPT_5_6_SOL, "gpt-5.6-sol", 500, 3000),
            (GPT_5_6_TERRA, "gpt-5.6-terra", 250, 1500),
            (GPT_5_6_LUNA, "gpt-5.6-luna", 100, 600),
            (CLAUDE_5_OPUS, "claude-opus-5", 500, 2500),
        )

        for model, model_id, input_cost, output_cost in expected_models:
            with self.subTest(model_id = model_id):
                self.assertEqual(model.id, model_id)
                self.assertEqual(model.types, expected_types)
                self.assertEqual(model.cost_estimate.input_1m_tokens, input_cost)
                self.assertEqual(model.cost_estimate.output_1m_tokens, output_cost)
                self.assertIn(model, ALL_EXTERNAL_TOOLS)

    def test_deprecated_text_models_are_not_available(self):
        available_ids = {tool.id for tool in ALL_EXTERNAL_TOOLS}
        deprecated_ids = {
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5.1",
            "gpt-5.2",
            "gpt-4o",
            "gpt-4o-mini",
            "claude-opus-4-7",
        }

        self.assertTrue(deprecated_ids.isdisjoint(available_ids))

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

    def test_adds_output_video_cost_by_size_and_duration(self):
        estimate = CostEstimate(
            output_video_1k_second = 2,
            output_video_2k_second = 4,
            output_video_4k_second = 8,
        )

        result = estimate.get_minimum_for(
            input_text = "",
            max_output_tokens = 0,
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

        self.assertEqual(result, 20.0)

    def test_video_catalog_models_have_expected_costs_and_reference_limits(self):
        expected_models = (
            (VIDEO_GEN_P_VIDEO, "prunaai/p-video", (2, 4, 4), 1),
            (VIDEO_GEN_SEEDANCE_2_0, "bytedance/seedance-2.0", (18, 45, 100), 9),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "bytedance/seedance-2.0-fast", (15, 15, 15), 9),
            (VIDEO_GEN_VEO_3_1, "google/veo-3.1", (40, 40, 40), 3),
            (VIDEO_GEN_VEO_3_1_FAST, "google/veo-3.1-fast", (15, 15, 15), 1),
            (VIDEO_GEN_RAY_3_2, "luma/ray-3.2", (15, 50, 50), 1),
        )

        for model, model_id, costs, max_input_images in expected_models:
            with self.subTest(model_id = model_id):
                self.assertEqual(model.id, model_id)
                self.assertEqual(model.types, [ToolType.videos_gen])
                self.assertEqual(model.max_input_images, max_input_images)
                self.assertEqual(model.cost_estimate.output_video_1k_second, costs[0])
                self.assertEqual(model.cost_estimate.output_video_2k_second, costs[1])
                self.assertEqual(model.cost_estimate.output_video_4k_second, costs[2])
                self.assertIn(model, ALL_EXTERNAL_TOOLS)

        self.assertIn("Video-Gen", REPLICATE.tools)

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
            ToolType.videos_gen,
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
