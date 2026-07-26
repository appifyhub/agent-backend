from dataclasses import dataclass
from enum import Enum

from features.images.image_size_utils import normalize_image_size_category


@dataclass(frozen = True)
class CostEstimate:
    """All costs are in credits."""
    input_1m_tokens: float | None = None
    output_1m_tokens: float | None = None
    search_1m_tokens: float | None = None
    input_image_1k: float | None = None
    input_image_2k: float | None = None
    input_image_4k: float | None = None
    input_image_8k: float | None = None
    input_image_12k: float | None = None
    output_image_1k: float | None = None
    output_image_2k: float | None = None
    output_image_4k: float | None = None
    output_video_1k_second: float | None = None
    output_video_2k_second: float | None = None
    output_video_4k_second: float | None = None
    api_call: float | None = None
    second_of_runtime: float | None = None
    web_search_query: float | None = None

    def get_minimum_for(
        self,
        input_text: str = "A",
        max_output_tokens: int = 1000,
        search_tokens: int = 1,
        runtime_seconds: float = 1.0,
        input_image_sizes: list[str] | None = None,
        output_image_sizes: list[str] | None = None,
        output_video_size: str | None = None,
        output_video_duration_seconds: float | None = None,
    ) -> float:
        input_tokens = max(1, len(input_text) // 4) if input_text else 0
        result = (input_tokens / 1_000_000) * (self.input_1m_tokens or 0)
        result += (max_output_tokens / 1_000_000) * (self.output_1m_tokens or 0)
        result += (search_tokens / 1_000_000) * (self.search_1m_tokens or 0)
        result += runtime_seconds * (self.second_of_runtime or 0)
        result += float(self.api_call or 0)
        result += float(self.web_search_query or 0)
        input_image_costs = {
            "1k": float(self.input_image_1k or 0),
            "2k": float(self.input_image_2k or 0),
            "4k": float(self.input_image_4k or 0),
            "8k": float(self.input_image_8k or 0),
            "12k": float(self.input_image_12k or 0),
        }
        fallback_input = float(self.input_image_1k or 0)
        for size in (input_image_sizes or []):
            normalized = normalize_image_size_category(size)
            result += input_image_costs.get(normalized, fallback_input)
        output_image_costs = {
            "1k": float(self.output_image_1k or 0),
            "2k": float(self.output_image_2k or 0),
            "4k": float(self.output_image_4k or 0),
        }
        fallback_output = float(self.output_image_1k or 0)
        for size in (output_image_sizes or []):
            normalized = normalize_image_size_category(size)
            result += output_image_costs.get(normalized, fallback_output)
        if output_video_duration_seconds is not None:
            output_video_costs = {
                "1k": float(self.output_video_1k_second or 0),
                "2k": float(self.output_video_2k_second or 0),
                "4k": float(self.output_video_4k_second or 0),
            }
            normalized = normalize_image_size_category(output_video_size or "1k")
            fallback_output_video = float(self.output_video_1k_second or 0)
            result += output_video_duration_seconds * output_video_costs.get(normalized, fallback_output_video)
        return result


@dataclass(frozen = True)
class ExternalToolProvider:
    id: str
    name: str
    token_management_url: str
    token_format: str
    tools: list[str]

    def __hash__(self) -> int:
        return hash(self.id)


# in sync with db.model.user.UserDB
class ToolType(str, Enum):
    chat = "chat"  # core chat models
    reasoning = "reasoning"  # reasoning models
    copywriting = "copywriting"  # cleanup models
    vision = "vision"  # vision features
    hearing = "hearing"  # hearing features
    images_gen = "images_gen"  # image generation
    videos_gen = "videos_gen"  # video generation
    images_edit = "images_edit"  # image editing
    search = "search"  # web search features
    embedding = "embedding"  # embedding models
    api_fiat_exchange = "api_fiat_exchange"  # fiat exchange API
    api_crypto_exchange = "api_crypto_exchange"  # crypto exchange API
    api_stock_quote = "api_stock_quote"  # stock quote API
    api_twitter = "api_twitter"  # X (Twitter) API
    credit_transfer = "credit_transfer"  # credit transfer between users
    deprecated = "deprecated"  # deprecated tool type, for API compatibility

    @property
    def output_token_multiplier(self) -> float:
        match self:
            case ToolType.chat:
                return 1.0
            case ToolType.reasoning:
                return 2.0
            case ToolType.copywriting:
                return 2.0
            case ToolType.vision:
                return 1.5
            case ToolType.search:
                return 2.0
            case _:
                return 0.0

    @property
    def temperature_percent(self) -> float:
        match self:
            case ToolType.chat:
                return 0.25
            case ToolType.reasoning:
                return 0.25
            case ToolType.copywriting:
                return 0.4
            case ToolType.vision:
                return 0.25
            case ToolType.search:
                return 0.35
            case _:
                return 0.0


@dataclass(frozen = True)
class ExternalTool:
    id: str
    name: str
    provider: ExternalToolProvider
    types: list[ToolType]
    cost_estimate: CostEstimate
    max_input_images: int = 0

    def __hash__(self) -> int:
        return hash(self.id)
