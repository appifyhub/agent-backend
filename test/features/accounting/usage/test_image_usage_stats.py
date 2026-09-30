import unittest

import stubs

from features.accounting.usage.image_usage_stats import ImageUsageStats


class ImageUsageStatsTest(unittest.TestCase):

    def test_from_replicate_prediction_with_metrics(self):
        prediction = stubs.external.replicate_prediction(metrics = {"predict_time": 5.5})

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertEqual(stats.remote_runtime_seconds, 5.5)
        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_replicate_prediction_with_int_predict_time(self):
        prediction = stubs.external.replicate_prediction(metrics = {"predict_time": 10})

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertEqual(stats.remote_runtime_seconds, 10)

    def test_from_replicate_prediction_with_no_metrics(self):
        prediction = stubs.external.replicate_prediction(metrics = None)

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_replicate_prediction_with_missing_predict_time(self):
        prediction = stubs.external.replicate_prediction(metrics = {"total_time": 8.0})

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_replicate_prediction_with_invalid_predict_time(self):
        prediction = stubs.external.replicate_prediction(metrics = {"predict_time": "not_a_number"})

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_google_sdk_response_with_all_fields(self):
        response = stubs.external.google_generate_content_response()

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 300)
        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_google_sdk_response_calculates_total_when_missing(self):
        response = stubs.external.google_generate_content_response(
            usage_metadata = {"prompt_token_count": 150, "candidates_token_count": 250},
        )

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 150)
        self.assertEqual(stats.output_tokens, 250)
        self.assertEqual(stats.total_tokens, 400)

    def test_from_google_sdk_response_with_partial_tokens(self):
        response = stubs.external.google_generate_content_response(usage_metadata = {"prompt_token_count": 100})

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertIsNone(stats.output_tokens)
        self.assertEqual(stats.total_tokens, 100)

    def test_from_google_sdk_response_with_no_usage_metadata(self):
        response = stubs.external.google_generate_content_response(usage_metadata = None)

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_google_sdk_response_does_not_calculate_when_both_none(self):
        response = stubs.external.google_generate_content_response(usage_metadata = {})

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_google_grounding_response_includes_thoughts(self):
        response = stubs.external.google_generate_content_response(
            usage_metadata = {
                "prompt_token_count": 19,
                "candidates_token_count": 282,
                "thoughts_token_count": 864,
                "total_token_count": 1165,
            },
        )

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertEqual(stats.input_tokens, 19)
        self.assertEqual(stats.output_tokens, 1146)  # 282 + 864
        self.assertEqual(stats.total_tokens, 1165)

    def test_from_google_grounding_response_no_thoughts(self):
        response = stubs.external.google_generate_content_response(
            usage_metadata = {
                "prompt_token_count": 50,
                "candidates_token_count": 200,
                "total_token_count": 250,
            },
        )

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertEqual(stats.input_tokens, 50)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 250)

    def test_from_google_grounding_response_no_usage_metadata(self):
        response = stubs.external.google_generate_content_response(usage_metadata = None)

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)
