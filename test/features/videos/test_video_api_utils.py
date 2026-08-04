import unittest

from features.external_tools.external_tool_library import (
    VIDEO_GEN_P_VIDEO,
    VIDEO_GEN_RAY_3_2,
    VIDEO_GEN_SEEDANCE_2_0,
    VIDEO_GEN_SEEDANCE_2_0_FAST,
    VIDEO_GEN_VEO_3_1,
    VIDEO_GEN_VEO_3_1_FAST,
)
from features.videos import video_api_utils


class VideoApiUtilsTest(unittest.TestCase):

    def test_resolve_aspect_ratio_uses_default_without_references(self):
        for tool in (
            VIDEO_GEN_P_VIDEO,
            VIDEO_GEN_SEEDANCE_2_0,
            VIDEO_GEN_SEEDANCE_2_0_FAST,
            VIDEO_GEN_VEO_3_1,
            VIDEO_GEN_VEO_3_1_FAST,
            VIDEO_GEN_RAY_3_2,
        ):
            with self.subTest(tool = tool.id):
                self.assertEqual(video_api_utils.resolve_aspect_ratio(tool, None), "16:9")

    def test_resolve_aspect_ratio_maps_omitted_ratio_for_model_input_mode(self):
        references = ["https://example.com/first.png", "https://example.com/second.png"]
        cases = [
            (VIDEO_GEN_P_VIDEO, None),
            (VIDEO_GEN_SEEDANCE_2_0, "adaptive"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "adaptive"),
            (VIDEO_GEN_VEO_3_1, "16:9"),
            (VIDEO_GEN_VEO_3_1_FAST, None),
            (VIDEO_GEN_RAY_3_2, None),
        ]

        for tool, expected in cases:
            with self.subTest(tool = tool.id):
                self.assertEqual(
                    video_api_utils.resolve_aspect_ratio(tool, None, references),
                    expected,
                )

    def test_resolve_aspect_ratio_maps_match_input_image_for_each_model(self):
        references = ["https://example.com/reference.png"]
        cases = [
            (VIDEO_GEN_P_VIDEO, None),
            (VIDEO_GEN_SEEDANCE_2_0, "adaptive"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "adaptive"),
            (VIDEO_GEN_VEO_3_1, None),
            (VIDEO_GEN_VEO_3_1_FAST, None),
            (VIDEO_GEN_RAY_3_2, None),
        ]

        for tool, expected in cases:
            with self.subTest(tool = tool.id):
                self.assertEqual(
                    video_api_utils.resolve_aspect_ratio(tool, "match_input_image", references),
                    expected,
                )

    def test_resolve_aspect_ratio_uses_each_models_closest_supported_ratio(self):
        cases = [
            (VIDEO_GEN_P_VIDEO, "21:9", "16:9"),
            (VIDEO_GEN_SEEDANCE_2_0, "2:3", "3:4"),
            (VIDEO_GEN_VEO_3_1, "1:1", "9:16"),
            (VIDEO_GEN_RAY_3_2, "3:2", "4:3"),
        ]

        for tool, requested, expected in cases:
            with self.subTest(tool = tool.id, requested = requested):
                self.assertEqual(video_api_utils.resolve_aspect_ratio(tool, requested), expected)

    def test_resolve_aspect_ratio_preserves_every_p_video_ratio(self):
        for aspect_ratio in video_api_utils.P_VIDEO_ASPECT_RATIOS:
            with self.subTest(aspect_ratio = aspect_ratio):
                self.assertEqual(
                    video_api_utils.resolve_aspect_ratio(VIDEO_GEN_P_VIDEO, aspect_ratio),
                    aspect_ratio,
                )

    def test_resolve_aspect_ratio_preserves_every_seedance_ratio(self):
        for tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            for aspect_ratio in video_api_utils.SEEDANCE_ASPECT_RATIOS:
                with self.subTest(tool = tool.id, aspect_ratio = aspect_ratio):
                    self.assertEqual(
                        video_api_utils.resolve_aspect_ratio(tool, aspect_ratio),
                        aspect_ratio,
                    )

    def test_resolve_aspect_ratio_does_not_expose_seedance_adaptive_input(self):
        for tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            with self.subTest(tool = tool.id):
                self.assertEqual(video_api_utils.resolve_aspect_ratio(tool, "adaptive"), "16:9")

    def test_resolve_aspect_ratio_preserves_every_veo_ratio(self):
        for tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
            for aspect_ratio in video_api_utils.VEO_ASPECT_RATIOS:
                with self.subTest(tool = tool.id, aspect_ratio = aspect_ratio):
                    self.assertEqual(
                        video_api_utils.resolve_aspect_ratio(tool, aspect_ratio),
                        aspect_ratio,
                    )

    def test_resolve_aspect_ratio_preserves_every_ray_ratio(self):
        for aspect_ratio in video_api_utils.RAY_ASPECT_RATIOS:
            with self.subTest(aspect_ratio = aspect_ratio):
                self.assertEqual(
                    video_api_utils.resolve_aspect_ratio(VIDEO_GEN_RAY_3_2, aspect_ratio),
                    aspect_ratio,
                )

    def test_resolve_aspect_ratio_invalid_format_defaults(self):
        self.assertEqual(video_api_utils.resolve_aspect_ratio(VIDEO_GEN_P_VIDEO, "invalid"), "16:9")

    def test_resolve_duration_defaults_to_medium(self):
        self.assertEqual(video_api_utils.resolve_duration(VIDEO_GEN_P_VIDEO, None), 5)
        self.assertEqual(video_api_utils.resolve_duration(VIDEO_GEN_P_VIDEO, "invalid"), 5)
        for tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            with self.subTest(tool = tool.id):
                self.assertEqual(video_api_utils.resolve_duration(tool, None), 5)
                self.assertEqual(video_api_utils.resolve_duration(tool, "-1"), 5)

    def test_resolve_duration_maps_p_video_and_seedance_tiers(self):
        for tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            for duration, expected in [("short", 4), ("medium", 5), ("long", 10)]:
                with self.subTest(tool = tool.id, duration = duration):
                    self.assertEqual(video_api_utils.resolve_duration(tool, duration.upper()), expected)

    def test_resolve_duration_maps_veo_tiers(self):
        for tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
            for duration, expected in [("short", 4), ("medium", 6), ("long", 8)]:
                with self.subTest(tool = tool.id, duration = duration):
                    self.assertEqual(video_api_utils.resolve_duration(tool, duration), expected)

    def test_resolve_duration_forces_veo_reference_images_to_8_seconds(self):
        for duration in ["short", "medium", "long"]:
            with self.subTest(duration = duration):
                self.assertEqual(
                    video_api_utils.resolve_duration(
                        VIDEO_GEN_VEO_3_1,
                        duration,
                        has_reference_images = True,
                    ),
                    8,
                )

    def test_resolve_duration_maps_ray_text_and_image_modes(self):
        for duration, expected in [("short", 5), ("medium", 5), ("long", 10)]:
            with self.subTest(mode = "text", duration = duration):
                self.assertEqual(video_api_utils.resolve_duration(VIDEO_GEN_RAY_3_2, duration), expected)
            with self.subTest(mode = "image", duration = duration):
                self.assertEqual(
                    video_api_utils.resolve_duration(
                        VIDEO_GEN_RAY_3_2,
                        duration,
                        has_input_image = True,
                    ),
                    5,
                )

    def test_map_to_model_parameters_maps_and_clamps_output_size(self):
        cases = [
            (VIDEO_GEN_P_VIDEO, "1K", "1K", "720p"),
            (VIDEO_GEN_P_VIDEO, "2K", "2K", "1080p"),
            (VIDEO_GEN_P_VIDEO, "4K", "2K", "1080p"),
            (VIDEO_GEN_SEEDANCE_2_0, "1K", "1K", "720p"),
            (VIDEO_GEN_SEEDANCE_2_0, "2K", "2K", "1080p"),
            (VIDEO_GEN_SEEDANCE_2_0, "4K", "4K", "4k"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "1K", "1K", "720p"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "2K", "1K", "720p"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "4K", "1K", "720p"),
            (VIDEO_GEN_VEO_3_1, "1K", "1K", "720p"),
            (VIDEO_GEN_VEO_3_1, "2K", "2K", "1080p"),
            (VIDEO_GEN_VEO_3_1, "4K", "2K", "1080p"),
            (VIDEO_GEN_VEO_3_1_FAST, "1K", "1K", "720p"),
            (VIDEO_GEN_VEO_3_1_FAST, "2K", "2K", "1080p"),
            (VIDEO_GEN_VEO_3_1_FAST, "4K", "2K", "1080p"),
            (VIDEO_GEN_RAY_3_2, "1K", "1K", "720p"),
            (VIDEO_GEN_RAY_3_2, "2K", "2K", "1080p"),
            (VIDEO_GEN_RAY_3_2, "4K", "2K", "1080p"),
        ]

        for tool, requested, expected_size, expected_resolution in cases:
            with self.subTest(tool = tool.id, requested = requested):
                result = video_api_utils.map_to_model_parameters(tool, output_size = requested)

                self.assertEqual(result.size, expected_size)
                self.assertEqual(result.resolution, expected_resolution)

    def test_map_to_model_parameters_defaults_invalid_output_size_to_1k(self):
        result = video_api_utils.map_to_model_parameters(VIDEO_GEN_P_VIDEO, output_size = "invalid")

        self.assertEqual(result.size, "1K")
        self.assertEqual(result.resolution, "720p")

    def test_map_to_model_parameters_uses_model_singular_image_field(self):
        reference = "https://example.com/first.png"

        for tool in (
            VIDEO_GEN_P_VIDEO,
            VIDEO_GEN_SEEDANCE_2_0,
            VIDEO_GEN_SEEDANCE_2_0_FAST,
            VIDEO_GEN_VEO_3_1,
            VIDEO_GEN_VEO_3_1_FAST,
        ):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    reference_image_urls = [reference],
                )

                self.assertEqual(result.image, reference)
                self.assertIsNone(result.start_image)
                self.assertIsNone(result.reference_images)

        ray_result = video_api_utils.map_to_model_parameters(
            VIDEO_GEN_RAY_3_2,
            reference_image_urls = [reference],
        )

        self.assertIsNone(ray_result.image)
        self.assertEqual(ray_result.start_image, reference)
        self.assertIsNone(ray_result.reference_images)

    def test_map_to_model_parameters_omits_ignored_anchor_aspect_ratio(self):
        reference = "https://example.com/first.png"

        for tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_RAY_3_2):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    aspect_ratio = "9:16",
                    reference_image_urls = [reference],
                )

                self.assertIsNone(result.aspect_ratio)

    def test_map_to_model_parameters_maps_match_input_image_like_image_models(self):
        reference = ["https://example.com/first.png"]

        for tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    aspect_ratio = "match_input_image",
                    reference_image_urls = reference,
                )
                self.assertEqual(result.aspect_ratio, "adaptive")

        for tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST, VIDEO_GEN_RAY_3_2):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    aspect_ratio = "match_input_image",
                    reference_image_urls = reference,
                )
                self.assertIsNone(result.aspect_ratio)

    def test_map_to_model_parameters_uses_supported_reference_arrays(self):
        references = [f"https://example.com/{index}.png" for index in range(11)]
        cases = [
            (VIDEO_GEN_SEEDANCE_2_0, 9),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, 9),
            (VIDEO_GEN_VEO_3_1, 3),
        ]

        for tool, expected_count in cases:
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    reference_image_urls = references,
                )

                self.assertIsNone(result.image)
                self.assertIsNone(result.start_image)
                self.assertEqual(result.reference_images, references[:expected_count])

    def test_map_to_model_parameters_falls_back_to_first_image_for_singular_models(self):
        references = ["https://example.com/first.png", "https://example.com/second.png"]

        for tool in (VIDEO_GEN_P_VIDEO, VIDEO_GEN_VEO_3_1_FAST, VIDEO_GEN_RAY_3_2):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    reference_image_urls = references,
                )

                self.assertEqual(result.image or result.start_image, references[0])
                self.assertIsNone(result.reference_images)

    def test_map_to_model_parameters_applies_veo_reference_requirements(self):
        result = video_api_utils.map_to_model_parameters(
            VIDEO_GEN_VEO_3_1,
            duration = "short",
            aspect_ratio = "9:16",
            reference_image_urls = ["https://example.com/first.png", "https://example.com/second.png"],
        )

        self.assertEqual(result.duration, 8)
        self.assertEqual(result.aspect_ratio, "16:9")

    def test_map_to_model_parameters_maps_veo_text_generation(self):
        for tool in (VIDEO_GEN_VEO_3_1, VIDEO_GEN_VEO_3_1_FAST):
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    prompt = "make a video",
                    duration = "medium",
                    aspect_ratio = "9:16",
                    output_size = "2K",
                )

                self.assertEqual(result.prompt, "make a video")
                self.assertEqual(result.duration, 6)
                self.assertEqual(result.aspect_ratio, "9:16")
                self.assertEqual(result.size, "2K")
                self.assertEqual(result.resolution, "1080p")
                self.assertIsNone(result.image)
                self.assertIsNone(result.reference_images)
                self.assertTrue(result.generate_audio)

    def test_map_to_model_parameters_maps_seedance_text_generation(self):
        cases = [
            (VIDEO_GEN_SEEDANCE_2_0, "2K", "1080p"),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "1K", "720p"),
        ]

        for tool, expected_size, expected_resolution in cases:
            with self.subTest(tool = tool.id):
                result = video_api_utils.map_to_model_parameters(
                    tool,
                    prompt = "make a video",
                    duration = "medium",
                    aspect_ratio = "21:9",
                    output_size = "2K",
                )

                self.assertEqual(result.prompt, "make a video")
                self.assertEqual(result.duration, 5)
                self.assertEqual(result.aspect_ratio, "21:9")
                self.assertEqual(result.size, expected_size)
                self.assertEqual(result.resolution, expected_resolution)
                self.assertIsNone(result.image)
                self.assertIsNone(result.reference_images)
                self.assertTrue(result.generate_audio)

    def test_seedance_cost_uses_mapped_size_and_duration(self):
        cases = [
            (VIDEO_GEN_SEEDANCE_2_0, "short", "1K", 72),
            (VIDEO_GEN_SEEDANCE_2_0, "medium", "2K", 225),
            (VIDEO_GEN_SEEDANCE_2_0, "long", "4K", 1000),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "short", "1K", 60),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "medium", "2K", 75),
            (VIDEO_GEN_SEEDANCE_2_0_FAST, "long", "4K", 150),
        ]

        for tool, duration, output_size, expected_cost in cases:
            with self.subTest(tool = tool.id, duration = duration, output_size = output_size):
                parameters = video_api_utils.map_to_model_parameters(
                    tool,
                    duration = duration,
                    output_size = output_size,
                )
                cost = tool.cost_estimate.get_minimum_for(
                    input_text = "",
                    max_output_tokens = 0,
                    output_video_size = parameters.size,
                    output_video_duration_seconds = parameters.duration,
                )

                self.assertEqual(cost, expected_cost)

    def test_map_to_model_parameters_maps_ray_text_generation(self):
        result = video_api_utils.map_to_model_parameters(
            VIDEO_GEN_RAY_3_2,
            prompt = "make a video",
            duration = "long",
            aspect_ratio = "21:9",
            output_size = "4K",
        )

        self.assertEqual(result.prompt, "make a video")
        self.assertEqual(result.duration, 10)
        self.assertEqual(result.aspect_ratio, "21:9")
        self.assertEqual(result.size, "2K")
        self.assertEqual(result.resolution, "1080p")
        self.assertIsNone(result.start_image)
        self.assertFalse(result.hdr)
        self.assertFalse(result.exr_export)
        self.assertFalse(result.loop)
        self.assertIsNone(result.save_audio)
        self.assertIsNone(result.generate_audio)

    def test_map_to_model_parameters_maps_ray_reference_generation(self):
        references = ["https://example.com/first.png", "https://example.com/second.png"]

        for duration in ("short", "medium", "long"):
            with self.subTest(duration = duration):
                result = video_api_utils.map_to_model_parameters(
                    VIDEO_GEN_RAY_3_2,
                    duration = duration,
                    aspect_ratio = "9:16",
                    reference_image_urls = references,
                )

                self.assertEqual(result.duration, 5)
                self.assertIsNone(result.aspect_ratio)
                self.assertEqual(result.start_image, references[0])
                self.assertIsNone(result.image)
                self.assertIsNone(result.reference_images)

    def test_ray_cost_uses_mapped_size_and_duration(self):
        cases = [
            ("short", "1K", None, 75),
            ("medium", "2K", None, 250),
            ("long", "4K", None, 500),
            ("long", "4K", ["https://example.com/first.png"], 250),
        ]

        for duration, output_size, references, expected_cost in cases:
            with self.subTest(duration = duration, output_size = output_size, references = references):
                parameters = video_api_utils.map_to_model_parameters(
                    VIDEO_GEN_RAY_3_2,
                    duration = duration,
                    output_size = output_size,
                    reference_image_urls = references,
                )
                cost = VIDEO_GEN_RAY_3_2.cost_estimate.get_minimum_for(
                    input_text = "",
                    max_output_tokens = 0,
                    output_video_size = parameters.size,
                    output_video_duration_seconds = parameters.duration,
                )

                self.assertEqual(cost, expected_cost)

    def test_map_to_model_parameters_applies_provider_defaults(self):
        p_video = video_api_utils.map_to_model_parameters(VIDEO_GEN_P_VIDEO)
        self.assertEqual(p_video.fps, 24)
        self.assertFalse(p_video.draft)
        self.assertFalse(p_video.prompt_upsampling)
        self.assertTrue(p_video.disable_safety_filter)
        self.assertTrue(p_video.save_audio)

        for tool in (
            VIDEO_GEN_SEEDANCE_2_0,
            VIDEO_GEN_SEEDANCE_2_0_FAST,
            VIDEO_GEN_VEO_3_1,
            VIDEO_GEN_VEO_3_1_FAST,
        ):
            with self.subTest(tool = tool.id):
                self.assertTrue(video_api_utils.map_to_model_parameters(tool).generate_audio)

        ray = video_api_utils.map_to_model_parameters(VIDEO_GEN_RAY_3_2)
        self.assertFalse(ray.hdr)
        self.assertFalse(ray.exr_export)
        self.assertFalse(ray.loop)

    def test_filter_replicate_params_keeps_only_selected_model_inputs(self):
        parameters = video_api_utils.map_to_model_parameters(
            VIDEO_GEN_P_VIDEO,
            prompt = "make a video",
            output_size = "4K",
            reference_image_urls = ["https://example.com/first.png"],
        )
        result = video_api_utils.filter_replicate_params(VIDEO_GEN_P_VIDEO, parameters)

        self.assertEqual(
            result,
            {
                "prompt": "make a video",
                "image": "https://example.com/first.png",
                "duration": 5,
                "resolution": "1080p",
                "fps": 24,
                "draft": False,
                "prompt_upsampling": False,
                "disable_safety_filter": True,
                "save_audio": True,
            },
        )

    def test_filter_replicate_params_omits_seedance_editing_inputs(self):
        for tool in (VIDEO_GEN_SEEDANCE_2_0, VIDEO_GEN_SEEDANCE_2_0_FAST):
            with self.subTest(tool = tool.id):
                parameters = video_api_utils.map_to_model_parameters(
                    tool,
                    reference_image_urls = [
                        "https://example.com/first.png",
                        "https://example.com/second.png",
                    ],
                )
                result = video_api_utils.filter_replicate_params(tool, parameters)

                self.assertEqual(result["reference_images"], parameters.reference_images)
                self.assertNotIn("image", result)
                self.assertNotIn("size", result)

    def test_filter_replicate_params_omits_ray_unsupported_inputs(self):
        parameters = video_api_utils.map_to_model_parameters(
            VIDEO_GEN_RAY_3_2,
            duration = "long",
            reference_image_urls = ["https://example.com/first.png"],
        )
        result = video_api_utils.filter_replicate_params(VIDEO_GEN_RAY_3_2, parameters)

        self.assertEqual(result["start_image"], parameters.start_image)
        self.assertEqual(result["duration"], 5)
        self.assertNotIn("aspect_ratio", result)
        self.assertNotIn("size", result)
        self.assertNotIn("generate_audio", result)
        self.assertNotIn("save_audio", result)

    def test_filter_replicate_params_matches_each_provider_schema(self):
        references = ["https://example.com/first.png", "https://example.com/second.png"]
        expected_keys = {
            VIDEO_GEN_P_VIDEO.id: {
                "prompt", "image", "duration", "resolution",
                "fps", "draft", "prompt_upsampling", "disable_safety_filter", "save_audio",
            },
            VIDEO_GEN_SEEDANCE_2_0.id: {
                "prompt", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
            },
            VIDEO_GEN_SEEDANCE_2_0_FAST.id: {
                "prompt", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
            },
            VIDEO_GEN_VEO_3_1.id: {
                "prompt", "reference_images", "duration", "aspect_ratio", "resolution", "generate_audio",
            },
            VIDEO_GEN_VEO_3_1_FAST.id: {
                "prompt", "image", "duration", "resolution", "generate_audio",
            },
            VIDEO_GEN_RAY_3_2.id: {
                "prompt", "start_image", "duration", "resolution", "hdr", "exr_export", "loop",
            },
        }

        for tool in (
            VIDEO_GEN_P_VIDEO,
            VIDEO_GEN_SEEDANCE_2_0,
            VIDEO_GEN_SEEDANCE_2_0_FAST,
            VIDEO_GEN_VEO_3_1,
            VIDEO_GEN_VEO_3_1_FAST,
            VIDEO_GEN_RAY_3_2,
        ):
            with self.subTest(tool = tool.id):
                parameters = video_api_utils.map_to_model_parameters(
                    tool,
                    prompt = "make a video",
                    reference_image_urls = references,
                )
                result = video_api_utils.filter_replicate_params(tool, parameters)

                self.assertEqual(set(result), expected_keys[tool.id])
