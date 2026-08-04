from time import monotonic, sleep, time
from typing import Any, Callable

from replicate.client import Client
from replicate.prediction import Prediction

from features.accounting.spending.spending_service import SpendingService
from features.accounting.usage.image_usage_stats import ImageUsageStats
from features.accounting.usage.proxies.namespace_proxy import NamespaceProxy
from features.accounting.usage.usage_tracking_service import UsageTrackingService
from features.external_tools.configured_tool import ConfiguredTool
from util import log
from util.error_codes import VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError

VIDEO_PREDICTION_TIMEOUT_SECONDS = 600
PREDICTION_POLL_INTERVAL_SECONDS = 5
TERMINAL_PREDICTION_STATUSES = {"succeeded", "failed", "canceled"}


class PredictionUsageTrackingDecorator:

    __start_timestamp: float
    __wrapped_prediction: Prediction
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool
    __rollback_db_session: Callable[[], None]
    __output_image_sizes: list[str] | None
    __input_image_sizes: list[str] | None
    __output_video_size: str | None
    __output_video_duration_seconds: float | None
    __result: Any | None
    __wait_error: Exception | None
    __wait_completed: bool

    def __init__(
        self,
        wrapped_prediction: Prediction,
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
        rollback_db_session: Callable[[], None],
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
        output_video_size: str | None = None,
        output_video_duration_seconds: float | None = None,
    ):
        self.__start_timestamp = time()
        self.__wrapped_prediction = wrapped_prediction
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool
        self.__rollback_db_session = rollback_db_session
        self.__output_image_sizes = output_image_sizes
        self.__input_image_sizes = input_image_sizes
        self.__output_video_size = output_video_size
        self.__output_video_duration_seconds = output_video_duration_seconds
        self.__result = None
        self.__wait_error = None
        self.__wait_completed = False

    def wait(self) -> Any:
        if self.__wait_completed:
            if self.__wait_error is not None:
                raise self.__wait_error
            return self.__result
        self.__rollback_db_session()
        try:
            is_video = self.__output_video_size is not None and self.__output_video_duration_seconds is not None
            result = self.__wait_for_video() if is_video else self.__wrapped_prediction.wait()
            self.__result = result
            runtime_seconds = time() - self.__start_timestamp
            self.__track_usage(runtime_seconds)
            self.__wait_completed = True
            return result
        except Exception as e:
            runtime_seconds = time() - self.__start_timestamp
            self.__track_failed_usage(runtime_seconds)
            self.__wait_error = e
            self.__wait_completed = True
            raise

    def __wait_for_video(self):
        deadline = monotonic() + VIDEO_PREDICTION_TIMEOUT_SECONDS
        while self.__wrapped_prediction.status not in TERMINAL_PREDICTION_STATUSES:
            remaining_seconds = deadline - monotonic()
            if remaining_seconds <= 0:
                try:
                    self.__wrapped_prediction.cancel()
                except Exception as e:
                    log.w(f"Could not cancel timed-out Replicate prediction '{self.__wrapped_prediction.id}'", e)
                raise ExternalServiceError("Replicate video generation timed out", VIDEO_GENERATION_FAILED)
            sleep(min(PREDICTION_POLL_INTERVAL_SECONDS, remaining_seconds))
            self.__wrapped_prediction.reload()

        if self.__wrapped_prediction.status != "succeeded":
            detail = self.__wrapped_prediction.error or self.__wrapped_prediction.logs or "unknown"
            raise ExternalServiceError(f"Replicate video generation ended with status '{self.__wrapped_prediction.status}': {detail}", VIDEO_GENERATION_FAILED)  # noqa: E501

    def __track_usage(self, runtime_seconds: float):
        stats = ImageUsageStats.from_replicate_prediction(self.__wrapped_prediction)
        if self.__output_video_size is not None and self.__output_video_duration_seconds is not None:
            record = self.__tracking_service.track_video_model(
                tool = self.__configured_tool.definition,
                tool_purpose = self.__configured_tool.purpose,
                runtime_seconds = runtime_seconds,
                payer_id = self.__configured_tool.payer_id,
                uses_credits = self.__configured_tool.uses_credits,
                output_video_size = self.__output_video_size,
                output_video_duration_seconds = self.__output_video_duration_seconds,
                remote_runtime_seconds = stats.remote_runtime_seconds,
            )
            self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)
            return

        record = self.__tracking_service.track_image_model(
            tool = self.__configured_tool.definition,
            tool_purpose = self.__configured_tool.purpose,
            runtime_seconds = runtime_seconds,
            payer_id = self.__configured_tool.payer_id,
            uses_credits = self.__configured_tool.uses_credits,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
            remote_runtime_seconds = stats.remote_runtime_seconds,
            input_tokens = stats.input_tokens,
            output_tokens = stats.output_tokens,
            total_tokens = stats.total_tokens,
        )
        self.__spending_service.deduct(self.__configured_tool, record.total_cost_credits)

    def __track_failed_usage(self, runtime_seconds: float):
        log.w(f"Tool call failed for {self.__configured_tool.definition.id}, tracking without deduction")
        if self.__output_video_size is not None and self.__output_video_duration_seconds is not None:
            stats = ImageUsageStats.from_replicate_prediction(self.__wrapped_prediction)
            self.__tracking_service.track_video_model(
                tool = self.__configured_tool.definition,
                tool_purpose = self.__configured_tool.purpose,
                runtime_seconds = runtime_seconds,
                payer_id = self.__configured_tool.payer_id,
                uses_credits = self.__configured_tool.uses_credits,
                output_video_size = self.__output_video_size,
                output_video_duration_seconds = self.__output_video_duration_seconds,
                remote_runtime_seconds = stats.remote_runtime_seconds,
                is_failed = True,
            )
            return

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

    @property
    def output(self) -> Any:
        return self.__wrapped_prediction.output

    @property
    def error(self) -> str | None:
        return self.__wrapped_prediction.error

    @property
    def logs(self) -> str | None:
        return self.__wrapped_prediction.logs

    @property
    def status(self) -> str:
        return self.__wrapped_prediction.status

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__wrapped_prediction, name)


class ReplicateUsageTrackingDecorator:

    __wrapped_client: Client
    __tracking_service: UsageTrackingService
    __spending_service: SpendingService
    __configured_tool: ConfiguredTool
    __rollback_db_session: Callable[[], None]
    __output_image_sizes: list[str] | None
    __input_image_sizes: list[str] | None
    __output_video_size: str | None
    __output_video_duration_seconds: float | None

    def __init__(
        self,
        wrapped_client: Client,
        tracking_service: UsageTrackingService,
        spending_service: SpendingService,
        configured_tool: ConfiguredTool,
        rollback_db_session: Callable[[], None],
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
        output_video_size: str | None = None,
        output_video_duration_seconds: float | None = None,
    ):
        self.__wrapped_client = wrapped_client
        self.__tracking_service = tracking_service
        self.__spending_service = spending_service
        self.__configured_tool = configured_tool
        self.__rollback_db_session = rollback_db_session
        self.__output_image_sizes = output_image_sizes
        self.__input_image_sizes = input_image_sizes
        self.__output_video_size = output_video_size
        self.__output_video_duration_seconds = output_video_duration_seconds

    @property
    def predictions(self) -> Any:
        return NamespaceProxy(
            self.__wrapped_client.predictions,
            self.__intercept_predictions_call,
        )

    def __intercept_predictions_call(self, name: str, attr: Any) -> Any:
        if name == "create":
            return self.__wrap_create(attr)
        return attr

    def __wrap_create(self, original_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(**kwargs: Any) -> PredictionUsageTrackingDecorator:
            self.__spending_service.validate_pre_flight(
                self.__configured_tool,
                input_image_sizes = self.__input_image_sizes,
                output_image_sizes = self.__output_image_sizes,
                output_video_size = self.__output_video_size,
                output_video_duration_seconds = self.__output_video_duration_seconds,
            )
            self.__rollback_db_session()
            prediction = original_method(**kwargs)
            return PredictionUsageTrackingDecorator(
                prediction,
                self.__tracking_service,
                self.__spending_service,
                self.__configured_tool,
                self.__rollback_db_session,
                self.__output_image_sizes,
                self.__input_image_sizes,
                self.__output_video_size,
                self.__output_video_duration_seconds,
            )
        return wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__wrapped_client, name)
