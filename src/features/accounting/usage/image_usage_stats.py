from dataclasses import dataclass
from typing import Any

from google.genai.types import GenerateContentResponse


@dataclass
class ImageUsageStats:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    remote_runtime_seconds: float | None = None

    @classmethod
    def from_replicate_prediction(
        cls,
        prediction: Any,
    ) -> "ImageUsageStats":
        remote_runtime_seconds = None
        metrics = getattr(prediction, "metrics", None)
        if metrics:
            gpu_time = getattr(metrics, "predict_time", None)
            if isinstance(gpu_time, (int, float)):
                remote_runtime_seconds = gpu_time

        return cls(
            remote_runtime_seconds = remote_runtime_seconds,
        )

    @classmethod
    def from_google_sdk_response(
        cls,
        response: GenerateContentResponse,
    ) -> "ImageUsageStats":
        input_tokens = None
        output_tokens = None
        total_tokens = None

        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            total_tokens = response.usage_metadata.total_token_count

        # total is not provided explicitly, but we can calculate it
        if (input_tokens is not None or output_tokens is not None) and total_tokens is None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0)

        return cls(
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            total_tokens = total_tokens,
        )

    @classmethod
    def from_google_grounding_response(
        cls,
        response: GenerateContentResponse,
    ) -> "ImageUsageStats":
        input_tokens = None
        output_tokens = None
        total_tokens = None

        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count
            candidates = response.usage_metadata.candidates_token_count or 0
            thoughts = response.usage_metadata.thoughts_token_count or 0
            output_tokens = candidates + thoughts
            total_tokens = response.usage_metadata.total_token_count

        if (input_tokens is not None or output_tokens is not None) and total_tokens is None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0)

        return cls(
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            total_tokens = total_tokens,
        )
