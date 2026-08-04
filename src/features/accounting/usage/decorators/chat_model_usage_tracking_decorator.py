from time import time
from typing import Any, Callable, Sequence

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableConfig

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.llm_usage_stats import LLMUsageStats
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from util import log


class RunnableUsageTrackingDecorator(Runnable[LanguageModelInput, AIMessage]):

    __wrapped_runnable: Runnable[LanguageModelInput, AIMessage]
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool
    __rollback_db_session: Callable[[], None]
    __max_tokens: int

    def __init__(
        self,
        wrapped_runnable: Runnable[LanguageModelInput, AIMessage],
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
        rollback_db_session: Callable[[], None],
        max_tokens: int,
    ):
        super().__init__()
        self.__wrapped_runnable = wrapped_runnable
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool
        self.__rollback_db_session = rollback_db_session
        self.__max_tokens = max_tokens

    def invoke(self, input: LanguageModelInput, config: RunnableConfig | None = None, **kwargs) -> AIMessage:
        self.__spending_service.validate_pre_flight(self.__configured_tool, self.__max_tokens, str(input))
        self.__rollback_db_session()
        start_time = time()
        try:
            response = self.__wrapped_runnable.invoke(input, config, **kwargs)
            runtime_seconds = time() - start_time
            self.__track_usage(response, runtime_seconds)
            return response
        except Exception:
            runtime_seconds = time() - start_time
            self.__track_failed_usage(runtime_seconds)
            raise

    def __track_usage(self, response: BaseMessage, runtime_seconds: float) -> None:
        llm_usage_stats = LLMUsageStats.from_response(response)
        record = self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            input_tokens = llm_usage_stats.input_tokens,
            output_tokens = llm_usage_stats.output_tokens,
            search_tokens = llm_usage_stats.search_tokens,
            total_tokens = llm_usage_stats.total_tokens,
        )
        self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_failed_usage(self, runtime_seconds: float) -> None:
        log.w(f"Tool call failed for {self.__configured_tool.definition.id}, tracking without deduction")
        self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            is_failed = True,
        )


class ChatModelUsageTrackingDecorator:

    __wrapped_model: BaseChatModel
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool
    __rollback_db_session: Callable[[], None]
    __max_tokens: int

    def __init__(
        self,
        wrapped_model: BaseChatModel,
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
        rollback_db_session: Callable[[], None],
        max_tokens: int,
    ):
        self.__wrapped_model = wrapped_model
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool
        self.__rollback_db_session = rollback_db_session
        self.__max_tokens = max_tokens

    def invoke(self, input: LanguageModelInput, config: RunnableConfig | None = None, **kwargs) -> AIMessage:
        self.__spending_service.validate_pre_flight(self.__configured_tool, self.__max_tokens, str(input))
        self.__rollback_db_session()
        start_time = time()
        try:
            response = self.__wrapped_model.invoke(input, config, **kwargs)
            runtime_seconds = time() - start_time
            self.__track_usage(response, runtime_seconds)
            return response
        except Exception:
            runtime_seconds = time() - start_time
            self.__track_failed_usage(runtime_seconds)
            raise

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[LanguageModelInput, AIMessage]:
        wrapped_runnable = self.__wrapped_model.bind_tools(tools, **kwargs)
        return RunnableUsageTrackingDecorator(
            wrapped_runnable,
            self.__tracking_service,
            self.__spending_service,
            self.__configured_tool,
            self.__rollback_db_session,
            self.__max_tokens,
        )

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        return self.__wrapped_model._generate(*args, **kwargs)

    @property
    def _llm_type(self) -> str:
        return self.__wrapped_model._llm_type

    def __track_usage(self, response: BaseMessage, runtime_seconds: float) -> None:
        llm_usage_stats = LLMUsageStats.from_response(response)
        record = self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            input_tokens = llm_usage_stats.input_tokens,
            output_tokens = llm_usage_stats.output_tokens,
            search_tokens = llm_usage_stats.search_tokens,
            total_tokens = llm_usage_stats.total_tokens,
        )
        self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_failed_usage(self, runtime_seconds: float) -> None:
        log.w(f"Tool call failed for {self.__configured_tool.definition.id}, tracking without deduction")
        self.__tracking_service.track_text_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            is_failed = True,
        )
