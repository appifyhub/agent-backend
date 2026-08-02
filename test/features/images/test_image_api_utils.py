import unittest

from features.external_tools.external_tool_library import (
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO,
    IMAGE_GEN_EDIT_GPT_IMAGE_2,
    IMAGE_GEN_EDIT_SEEDREAM_4_5,
)
from features.images import image_api_utils


class ImageApiUtilsTest(unittest.TestCase):

    def test_resolve_aspect_ratio_none_for_generation(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, None)
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_none_with_references_ignores_tool_purpose(self):
        input_urls = ["https://example.com/image.png"]
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, None, input_urls)
        self.assertEqual(result, "match_input_image")

    def test_resolve_aspect_ratio_none_for_editing_without_files(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, None)
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_valid_ratio(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "1:1")
        self.assertEqual(result, "1:1")

    def test_resolve_aspect_ratio_valid_ratio_portrait(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2:3")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_16_9(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "16:9")
        self.assertEqual(result, "16:9")

    def test_resolve_aspect_ratio_match_input_image_with_references_ignores_tool_purpose(self):
        input_urls = ["https://example.com/image.png"]
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "match_input_image", input_urls)
        self.assertEqual(result, "match_input_image")

    def test_resolve_aspect_ratio_match_input_image_without_files_falls_back(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "match_input_image")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_match_input_image_for_generation_falls_back(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "match_input_image")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_with_spaces(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2 : 3")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_with_multiple_spaces(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "  1  :  1  ")
        self.assertEqual(result, "1:1")

    def test_resolve_aspect_ratio_with_tabs(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "1\t:\t1")
        self.assertEqual(result, "1:1")

    def test_resolve_aspect_ratio_closest_match_slightly_off(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2.1:3")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_closest_match_between_two(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "3.5:4")
        self.assertIn(result, ["3:4", "1:1"])

    def test_resolve_aspect_ratio_closest_match_landscape(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "3.8:2")
        self.assertEqual(result, "16:9")

    def test_resolve_aspect_ratio_invalid_format_no_colon(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2x3")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_invalid_format_multiple_colons(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2:3:4")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_invalid_non_numeric(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "a:b")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_zero_division(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "2:0")
        self.assertEqual(result, "2:3")

    def test_resolve_aspect_ratio_invalid_with_references_uses_input_image_default(self):
        input_urls = ["https://example.com/image.png"]
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "invalid", input_urls)
        self.assertEqual(result, "match_input_image")

    def test_map_to_model_parameters_single_image_model_uses_singular_fields_only(self):
        input_urls = ["https://example.com/one.png", "https://example.com/two.png"]

        result = image_api_utils.map_to_model_parameters(
            tool = IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO,  # max_input_images = 1
            prompt = "test prompt",
            aspect_ratio = "1:1",
            output_size = "2K",
            input_urls = input_urls,
        )

        self.assertEqual(result.image, input_urls[0])
        self.assertEqual(result.input_image, input_urls[0])
        self.assertIsNone(result.image_input)
        self.assertIsNone(result.input_images)

    def test_map_to_model_parameters_multi_image_model_uses_list_fields(self):
        input_urls = ["https://example.com/one.png", "https://example.com/two.png"]

        result = image_api_utils.map_to_model_parameters(
            tool = IMAGE_GEN_EDIT_FLUX_2_PRO,  # max_input_images = 8
            prompt = "test prompt",
            aspect_ratio = "1:1",
            output_size = "2K",
            input_urls = input_urls,
        )

        self.assertEqual(result.image, input_urls[0])
        self.assertEqual(result.input_image, input_urls[0])
        self.assertIsNotNone(result.image_input)
        self.assertIsNotNone(result.input_images)
        self.assertEqual(len(result.image_input), 2)
        self.assertEqual(len(result.input_images), 2)
        self.assertEqual(result.image_input, input_urls)
        self.assertEqual(result.input_images, input_urls)

    def test_map_to_model_parameters_gpt_image_2_returns_unified_params(self):
        result = image_api_utils.map_to_model_parameters(
            tool = IMAGE_GEN_EDIT_GPT_IMAGE_2,
            prompt = "test prompt",
            output_size = "2K",
        )
        self.assertEqual(result.prompt, "test prompt")
        self.assertEqual(result.size, "2K")
        self.assertIsNone(result.resolution)

    def test_filter_replicate_params_seedream_4_5_strips_disallowed(self):
        params = {
            "prompt": "test",
            "size": "2K",
            "aspect_ratio": "2:3",
            "max_images": 1,
            "disable_safety_checker": True,
            "sequential_image_generation": "disabled",
            "image_input": None,
            "quality": "high",
            "output_format": "png",
            "num_inference_steps": 30,
            "prompt_upsampling": False,
        }
        result = image_api_utils.filter_replicate_params(IMAGE_GEN_EDIT_SEEDREAM_4_5, params)
        self.assertEqual(set(result.keys()), {
            "prompt", "size", "aspect_ratio", "max_images",
            "disable_safety_checker", "sequential_image_generation", "image_input",
        })

    def test_filter_replicate_params_non_allowlisted_model_passes_through(self):
        params = {"prompt": "test", "quality": "high", "num_inference_steps": 30}
        result = image_api_utils.filter_replicate_params(IMAGE_GEN_EDIT_FLUX_2_PRO, params)
        self.assertEqual(result, params)
