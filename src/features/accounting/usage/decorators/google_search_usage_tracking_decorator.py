from time import time
from typing import Any, Callable

from google.genai.client import Client as GoogleSDKClient
from google.genai.models import Models as GoogleSDKModels
from google.genai.types import GenerateContentResponse

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.image_usage_stats import ImageUsageStats
from features.accounting.usage.proxies.namespace_proxy import NamespaceProxy
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from util import log


class GoogleSearchUsageTrackingDecorator:

    __wrapped_client: GoogleSDKClient
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool

    def __init__(
        self,
        wrapped_client: GoogleSDKClient,
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
    ):
        self.__wrapped_client = wrapped_client
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool

    @property
    def models(self) -> GoogleSDKModels:
        return NamespaceProxy(
            self.__wrapped_client.models,
            self.__intercept_models_call,
        )  # type: ignore

    def __intercept_models_call(self, name: str, attr: Any) -> Any:
        if name == "generate_content":
            return self.__wrap_generate_content(attr)
        return attr

    def __wrap_generate_content(self, original_method: Callable[..., Any]) -> Callable[..., GenerateContentResponse]:
        def wrapper(*args: Any, **kwargs: Any) -> GenerateContentResponse:
            self.__spending_service.validate_pre_flight(self.__configured_tool)
            start_time = time()
            try:
                response: GenerateContentResponse = original_method(*args, **kwargs)
                runtime_seconds = time() - start_time
                self.__track_usage(response, runtime_seconds)
                return response
            except Exception:
                runtime_seconds = time() - start_time
                self.__track_failed_usage(runtime_seconds)
                raise
        return wrapper

    def __track_usage(self, response: GenerateContentResponse, runtime_seconds: float) -> None:
        usage_stats = ImageUsageStats.from_google_grounding_response(response)
        token_record = self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            input_tokens = usage_stats.input_tokens,
            output_tokens = usage_stats.output_tokens,
            total_tokens = usage_stats.total_tokens,
        )
        self.__spending_service.deduct(self.__configured_tool, token_record.total_cost_credits)

        grounding = response.candidates[0].grounding_metadata if response.candidates else None
        query_count = len((grounding.web_search_queries or []) if grounding else [])
        if query_count > 0:
            query_records = self.__tracking_service.track_web_search_query(
                tool = self.__configured_tool.definition,
                tool_purpose = self.__configured_tool.purpose,
                runtime_seconds = runtime_seconds,
                payer_id = self.__configured_tool.payer_id,
                uses_credits = self.__configured_tool.uses_credits,
                query_count = query_count,
            )
            for record in query_records:
                self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_failed_usage(self, runtime_seconds: float) -> None:
        log.w(f"Google search failed for {self.__configured_tool.definition.id}, tracking without deduction")
        self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            is_failed = True,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__wrapped_client, name)
