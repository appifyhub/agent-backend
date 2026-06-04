import unittest
from unittest.mock import Mock

from google.genai.types import GenerateContentResponse

from features.accounting.usage.image_usage_stats import ImageUsageStats


class ImageUsageStatsTest(unittest.TestCase):

    def test_from_replicate_prediction_with_metrics(self):
        prediction = Mock()
        prediction.metrics = Mock()
        prediction.metrics.predict_time = 5.5

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertEqual(stats.remote_runtime_seconds, 5.5)
        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_replicate_prediction_with_int_predict_time(self):
        prediction = Mock()
        prediction.metrics = Mock()
        prediction.metrics.predict_time = 10

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertEqual(stats.remote_runtime_seconds, 10)

    def test_from_replicate_prediction_with_no_metrics(self):
        prediction = Mock()
        prediction.metrics = None

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_replicate_prediction_with_missing_predict_time(self):
        prediction = Mock()
        prediction.metrics = Mock(spec = [])

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_replicate_prediction_with_invalid_predict_time(self):
        prediction = Mock()
        prediction.metrics = Mock()
        prediction.metrics.predict_time = "not_a_number"

        stats = ImageUsageStats.from_replicate_prediction(prediction)

        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_google_sdk_response_with_all_fields(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 100
        response.usage_metadata.candidates_token_count = 200
        response.usage_metadata.total_token_count = 300

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 300)
        self.assertIsNone(stats.remote_runtime_seconds)

    def test_from_google_sdk_response_calculates_total_when_missing(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 150
        response.usage_metadata.candidates_token_count = 250
        response.usage_metadata.total_token_count = None

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 150)
        self.assertEqual(stats.output_tokens, 250)
        self.assertEqual(stats.total_tokens, 400)

    def test_from_google_sdk_response_with_partial_tokens(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 100
        response.usage_metadata.candidates_token_count = None
        response.usage_metadata.total_token_count = None

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertEqual(stats.input_tokens, 100)
        self.assertIsNone(stats.output_tokens)
        self.assertEqual(stats.total_tokens, 100)

    def test_from_google_sdk_response_with_no_usage_metadata(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = None

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_google_sdk_response_does_not_calculate_when_both_none(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = None
        response.usage_metadata.candidates_token_count = None
        response.usage_metadata.total_token_count = None

        stats = ImageUsageStats.from_google_sdk_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)

    def test_from_google_grounding_response_includes_thoughts(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 19
        response.usage_metadata.candidates_token_count = 282
        response.usage_metadata.thoughts_token_count = 864
        response.usage_metadata.total_token_count = 1165

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertEqual(stats.input_tokens, 19)
        self.assertEqual(stats.output_tokens, 1146)  # 282 + 864
        self.assertEqual(stats.total_tokens, 1165)

    def test_from_google_grounding_response_no_thoughts(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = Mock()
        response.usage_metadata.prompt_token_count = 50
        response.usage_metadata.candidates_token_count = 200
        response.usage_metadata.thoughts_token_count = None
        response.usage_metadata.total_token_count = 250

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertEqual(stats.input_tokens, 50)
        self.assertEqual(stats.output_tokens, 200)
        self.assertEqual(stats.total_tokens, 250)

    def test_from_google_grounding_response_no_usage_metadata(self):
        response = Mock(spec = GenerateContentResponse)
        response.usage_metadata = None

        stats = ImageUsageStats.from_google_grounding_response(response)

        self.assertIsNone(stats.input_tokens)
        self.assertIsNone(stats.output_tokens)
        self.assertIsNone(stats.total_tokens)
