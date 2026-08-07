import unittest

from features.external_tools.external_tool_library import (
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO,
    IMAGE_GEN_EDIT_GPT_IMAGE_2,
    IMAGE_GEN_EDIT_SEEDREAM_4_5,
    IMAGE_GEN_EDIT_SEEDREAM_5_PRO,
)
from features.images import image_api_utils


class ImageApiUtilsTest(unittest.TestCase):

    def test_resolve_aspect_ratio_omitted_defaults_by_reference_presence(self):
        self.assertEqual(image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, None), "2:3")
        self.assertEqual(
            image_api_utils.resolve_aspect_ratio(
                IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, None, ["https://example.com/image.png"],
            ),
            "match_input_image",
        )

    def test_resolve_aspect_ratio_preserves_every_supported_ratio(self):
        for aspect_ratio in image_api_utils.VALID_ASPECT_RATIOS:
            with self.subTest(aspect_ratio = aspect_ratio):
                self.assertEqual(
                    image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, aspect_ratio),
                    aspect_ratio,
                )

    def test_resolve_aspect_ratio_match_input_image_requires_references(self):
        self.assertEqual(
            image_api_utils.resolve_aspect_ratio(
                IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "match_input_image", ["https://example.com/image.png"],
            ),
            "match_input_image",
        )
        self.assertEqual(
            image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "match_input_image"),
            "2:3",
        )

    def test_resolve_aspect_ratio_ignores_surrounding_whitespace(self):
        result = image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, "  1 \t:\t 1  ")
        self.assertEqual(result, "1:1")

    def test_resolve_aspect_ratio_maps_unsupported_to_closest_supported(self):
        cases = [("2.1:3", "2:3"), ("3.8:2", "16:9"), ("21:9", "16:9")]
        for requested, expected in cases:
            with self.subTest(requested = requested):
                self.assertEqual(
                    image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, requested),
                    expected,
                )

    def test_resolve_aspect_ratio_unparseable_falls_back_to_default(self):
        for requested in ["2x3", "2:3:4", "a:b", "2:0"]:
            with self.subTest(requested = requested):
                self.assertEqual(
                    image_api_utils.resolve_aspect_ratio(IMAGE_GEN_EDIT_FLUX_KONTEXT_PRO, requested),
                    "2:3",
                )

    def test_resolve_aspect_ratio_unparseable_with_references_uses_input_image_default(self):
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
        parameters = image_api_utils.map_to_model_parameters(
            IMAGE_GEN_EDIT_SEEDREAM_4_5,
            prompt = "test",
            input_urls = ["https://example.com/reference.png"],
        )

        result = image_api_utils.filter_replicate_params(IMAGE_GEN_EDIT_SEEDREAM_4_5, parameters)

        self.assertEqual(set(result.keys()), {
            "prompt", "size", "aspect_ratio", "max_images",
            "disable_safety_checker", "sequential_image_generation", "image_input",
        })

    def test_map_to_model_parameters_seedream_5_pro_normalizes_size(self):
        for output_size, expected in [("1K", "1K"), ("2K", "2K"), ("4K", "2K")]:
            with self.subTest(output_size = output_size):
                result = image_api_utils.map_to_model_parameters(
                    IMAGE_GEN_EDIT_SEEDREAM_5_PRO,
                    prompt = "test",
                    output_size = output_size,
                )

                self.assertEqual(result.size, expected)

    def test_filter_replicate_params_seedream_5_pro_uses_exact_schema(self):
        input_urls = ["https://example.com/one.png", "https://example.com/two.png"]
        parameters = image_api_utils.map_to_model_parameters(
            IMAGE_GEN_EDIT_SEEDREAM_5_PRO,
            prompt = "test",
            input_urls = input_urls,
        )

        result = image_api_utils.filter_replicate_params(IMAGE_GEN_EDIT_SEEDREAM_5_PRO, parameters)

        self.assertEqual(result, {
            "prompt": "test",
            "aspect_ratio": "match_input_image",
            "size": "2K",
            "output_format": "png",
            "image_input": input_urls,
        })

    def test_filter_replicate_params_non_allowlisted_model_passes_through(self):
        parameters = image_api_utils.map_to_model_parameters(IMAGE_GEN_EDIT_FLUX_2_PRO, prompt = "test")

        result = image_api_utils.filter_replicate_params(IMAGE_GEN_EDIT_FLUX_2_PRO, parameters)

        self.assertEqual(result["prompt"], "test")
        self.assertEqual(result["quality"], "high")
        self.assertEqual(result["num_inference_steps"], 30)
        self.assertNotIn("image", result)
