from dataclasses import replace

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from util import log
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, USER_NOT_FOUND
from util.errors import NotFoundError, ValidationError


class SpendingService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_pre_flight(
        self,
        configured_tool: ConfiguredTool,
        max_output_tokens: int = config.default_max_output_tokens,
        input_text: str = "",
        search_tokens: int = 0,
        runtime_seconds: float = 0.0,
        input_image_sizes: list[str] | None = None,
        output_image_sizes: list[str] | None = None,
        output_video_size: str | None = None,
        output_video_duration_seconds: float | None = None,
    ) -> None:
        if not configured_tool.uses_credits:
            return
        estimated_cost = configured_tool.definition.cost_estimate.get_minimum_for(
            input_text = input_text,
            max_output_tokens = max_output_tokens,
            search_tokens = search_tokens,
            runtime_seconds = runtime_seconds,
            input_image_sizes = input_image_sizes,
            output_image_sizes = output_image_sizes,
            output_video_size = output_video_size,
            output_video_duration_seconds = output_video_duration_seconds,
        ) + config.usage_maintenance_fee_credits
        user = self.__di.user_repo.get(configured_tool.payer_id)
        if user is None:
            raise NotFoundError(f"Payer user not found for id {configured_tool.payer_id}", USER_NOT_FOUND)
        if user.credit_balance < estimated_cost:
            raise ValidationError(f"Insufficient credits: minimum required {estimated_cost}, available {user.credit_balance}", INSUFFICIENT_CREDITS)  # noqa: E501

    def deduct(self, configured_tool: ConfiguredTool, amount: float) -> None:
        if not configured_tool.uses_credits:
            return

        def apply(user):
            available = user.credit_balance or 0.0
            if amount > available:
                log.w(
                    f"Actual cost {amount} exceeds pre-flight estimate for user "
                    f"{configured_tool.payer_id}; balance will go negative",
                )
            return replace(user, credit_balance = available - amount)
        self.__di.user_repo.update_locked(configured_tool.payer_id, apply)
