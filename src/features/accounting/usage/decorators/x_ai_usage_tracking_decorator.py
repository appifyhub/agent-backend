from time import time
from typing import Any, Callable

from xai_sdk import Client as XAISDKClient

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.proxies.namespace_proxy import NamespaceProxy
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from util import log
from util.error_codes import LLM_UNEXPECTED_RESPONSE
from util.errors import ExternalServiceError

X_AI_USD_TICKS_PER_CREDIT = 100_000_000


class XAIUsageTrackingDecorator:

    __wrapped_client: XAISDKClient
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool
    __rollback_db_session: Callable[[], None]
    __output_image_sizes: list[str] | None
    __input_image_sizes: list[str] | None

    def __init__(
        self,
        wrapped_client: XAISDKClient,
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
        rollback_db_session: Callable[[], None],
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
    ):
        self.__wrapped_client = wrapped_client
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool
        self.__rollback_db_session = rollback_db_session
        self.__output_image_sizes = output_image_sizes
        self.__input_image_sizes = input_image_sizes

    @property
    def image(self) -> Any:
        return NamespaceProxy(
            self.__wrapped_client.image,
            self.__intercept_image_call,
        )

    @property
    def chat(self) -> Any:
        return NamespaceProxy(
            self.__wrapped_client.chat,
            self.__intercept_chat_call,
        )

    def __intercept_image_call(self, name: str, attr: Any) -> Any:
        if name == "sample":
            return self.__wrap_image_sample(attr)
        return attr

    def __intercept_chat_call(self, name: str, attr: Any) -> Any:
        if name == "create":
            return self.__wrap_chat_create(attr)
        return attr

    def __wrap_image_sample(self, original_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.__spending_service.validate_pre_flight(
                self.__configured_tool,
                input_image_sizes = self.__input_image_sizes,
                output_image_sizes = self.__output_image_sizes,
            )
            self.__rollback_db_session()
            start_time = time()
            try:
                response = original_method(*args, **kwargs)
                runtime_seconds = time() - start_time
                self.__track_image_usage(runtime_seconds)
                return response
            except Exception:
                runtime_seconds = time() - start_time
                self.__track_failed_image_usage(runtime_seconds)
                raise
        return wrapper

    def __wrap_chat_create(self, original_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            chat = original_method(*args, **kwargs)
            return NamespaceProxy(chat, self.__intercept_chat_instance_call)
        return wrapper

    def __intercept_chat_instance_call(self, name: str, attr: Any) -> Any:
        if name == "sample":
            return self.__wrap_chat_sample(attr)
        return attr

    def __wrap_chat_sample(self, original_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.__spending_service.validate_pre_flight(self.__configured_tool)
            start_time = time()
            try:
                response = original_method(*args, **kwargs)
                runtime_seconds = time() - start_time
                self.__track_chat_usage(response, runtime_seconds)
                return response
            except Exception:
                runtime_seconds = time() - start_time
                self.__track_failed_chat_usage(runtime_seconds)
                raise
        return wrapper

    def __track_image_usage(self, runtime_seconds: float) -> None:
        record = self.__tracking_service.track_image_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
        )
        self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_chat_usage(self, response: Any, runtime_seconds: float) -> None:
        usage = getattr(response, "usage", None)
        cost_ticks = getattr(usage, "cost_in_usd_ticks", None)
        if cost_ticks is None:
            raise ExternalServiceError(
                "xAI response did not include provider-reported cost",
                LLM_UNEXPECTED_RESPONSE,
            )

        server_side_tool_usage = getattr(response, "server_side_tool_usage", None)
        if server_side_tool_usage:
            log.d(f"xAI server-side tools used: {server_side_tool_usage}")

        record = self.__tracking_service.track_provider_reported_cost(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            provider_cost_credits = float(cost_ticks) / X_AI_USD_TICKS_PER_CREDIT,
            input_tokens = self.__get_usage_value(usage, "input_tokens", "prompt_tokens"),
            output_tokens = self.__get_usage_value(usage, "output_tokens", "completion_tokens"),
            total_tokens = self.__get_usage_value(usage, "total_tokens"),
        )
        self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_failed_image_usage(self, runtime_seconds: float) -> None:
        log.w(f"Tool call failed for {self.__configured_tool.definition.id}, tracking without deduction")
        self.__tracking_service.track_image_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
            is_failed = True,
        )

    def __track_failed_chat_usage(self, runtime_seconds: float) -> None:
        log.w(f"Tool call failed for {self.__configured_tool.definition.id}, tracking without deduction")
        self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            is_failed = True,
        )

    def __get_usage_value(self, usage: Any, *names: str) -> int | None:
        for name in names:
            value = getattr(usage, name, None)
            if isinstance(value, int):
                return value
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__wrapped_client, name)
