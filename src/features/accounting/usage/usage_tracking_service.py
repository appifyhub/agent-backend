from datetime import datetime, timezone
from uuid import UUID

from di.di import DI
from features.accounting.usage.participant_details import ParticipantDetails, ParticipantInfo
from features.accounting.usage.usage_record import UsageRecord
from features.external_tools.external_tool import CostEstimate, ExternalTool, ToolType
from features.images.image_size_utils import normalize_image_size_category
from features.integrations.integrations import user_to_participant
from util import log
from util.config import config


class UsageTrackingService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def track_text_model(
        self,
        tool: ExternalTool,
        tool_purpose: ToolType,
        runtime_seconds: float,
        payer_id: UUID,
        uses_credits: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        search_tokens: int | None = None,
        total_tokens: int | None = None,
        remote_runtime_seconds: float | None = None,
        is_failed: bool = False,
    ) -> UsageRecord:
        has_token_usage = any(t is not None for t in [input_tokens, output_tokens, search_tokens, total_tokens])
        has_duration_usage = remote_runtime_seconds is not None
        if not is_failed and not has_token_usage and not has_duration_usage:
            log.e(f"No usage metadata available for LLM {tool.id} - all token and duration fields are None")

        model_cost_credits: float = self.__calculate_llm_cost(tool.cost_estimate, input_tokens, output_tokens, search_tokens)
        remote_runtime_cost_credits: float = (tool.cost_estimate.second_of_runtime or 0) \
            * (remote_runtime_seconds or runtime_seconds)
        api_cost_credits: float = float(tool.cost_estimate.api_call or 0)
        maintenance_fee_credits: float = config.usage_maintenance_fee_credits
        total_cost_credits: float = model_cost_credits + api_cost_credits + remote_runtime_cost_credits + maintenance_fee_credits

        record = UsageRecord(
            user_id = self.__di.invoker.id,
            payer_id = payer_id,
            uses_credits = uses_credits,
            is_failed = is_failed,
            chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
            tool = tool,
            tool_purpose = tool_purpose,
            timestamp = datetime.now(timezone.utc),
            model_cost_credits = model_cost_credits,
            api_call_cost_credits = api_cost_credits,
            remote_runtime_cost_credits = remote_runtime_cost_credits,
            maintenance_fee_credits = maintenance_fee_credits,
            total_cost_credits = total_cost_credits,
            runtime_seconds = runtime_seconds,
            remote_runtime_seconds = remote_runtime_seconds,
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            total_tokens = total_tokens,
            search_tokens = search_tokens,
            participant_details = self.__build_participant_details(payer_id),
        )
        return self.__di.usage_record_repo.create(record)

    def track_image_model(
        self,
        tool: ExternalTool,
        tool_purpose: ToolType,
        runtime_seconds: float,
        payer_id: UUID,
        uses_credits: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
        remote_runtime_seconds: float | None = None,
        is_failed: bool = False,
    ) -> UsageRecord:
        has_token_usage = any(t is not None for t in [input_tokens, output_tokens, total_tokens])
        has_image_sizes = bool(output_image_sizes or input_image_sizes)
        if not is_failed and not has_token_usage and not has_image_sizes:
            log.e(f"No usage metadata available for image tool {tool.id} - all metrics (tokens, sizes) are None")

        model_cost_credits: float = self.__calculate_image_cost(
            tool.cost_estimate, output_image_sizes, input_image_sizes, input_tokens, output_tokens, total_tokens,
        )
        api_cost_credits: float = float(tool.cost_estimate.api_call or 0)
        remote_runtime_cost_credits: float = (tool.cost_estimate.second_of_runtime or 0) \
            * (remote_runtime_seconds or runtime_seconds)
        maintenance_fee_credits: float = config.usage_maintenance_fee_credits
        total_cost_credits: float = model_cost_credits + api_cost_credits + remote_runtime_cost_credits + maintenance_fee_credits

        record = UsageRecord(
            user_id = self.__di.invoker.id,
            payer_id = payer_id,
            uses_credits = uses_credits,
            is_failed = is_failed,
            chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
            tool = tool,
            tool_purpose = tool_purpose,
            timestamp = datetime.now(timezone.utc),
            model_cost_credits = model_cost_credits,
            remote_runtime_cost_credits = remote_runtime_cost_credits,
            api_call_cost_credits = api_cost_credits,
            maintenance_fee_credits = maintenance_fee_credits,
            total_cost_credits = total_cost_credits,
            runtime_seconds = runtime_seconds,
            remote_runtime_seconds = remote_runtime_seconds,
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            total_tokens = total_tokens,
            output_image_sizes = output_image_sizes,
            input_image_sizes = input_image_sizes,
            participant_details = self.__build_participant_details(payer_id),
        )
        return self.__di.usage_record_repo.create(record)

    def track_web_search_query(
        self,
        tool: ExternalTool,
        tool_purpose: ToolType,
        runtime_seconds: float,
        payer_id: UUID,
        uses_credits: bool,
        query_count: int,
        is_failed: bool = False,
    ) -> list[UsageRecord]:
        per_query_cost: float = float(tool.cost_estimate.web_search_query or 0)
        records: list[UsageRecord] = []
        for _ in range(max(query_count, 0)):
            record = UsageRecord(
                user_id = self.__di.invoker.id,
                payer_id = payer_id,
                uses_credits = uses_credits,
                is_failed = is_failed,
                chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
                tool = tool,
                tool_purpose = tool_purpose,
                timestamp = datetime.now(timezone.utc),
                model_cost_credits = 0.0,
                remote_runtime_cost_credits = 0.0,
                api_call_cost_credits = per_query_cost,
                maintenance_fee_credits = 0.0,
                total_cost_credits = per_query_cost,
                runtime_seconds = runtime_seconds,
                participant_details = self.__build_participant_details(payer_id),
            )
            records.append(self.__di.usage_record_repo.create(record))
        return records

    def track_provider_reported_cost(
        self,
        tool: ExternalTool,
        tool_purpose: ToolType,
        runtime_seconds: float,
        payer_id: UUID,
        uses_credits: bool,
        provider_cost_credits: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        is_failed: bool = False,
    ) -> UsageRecord:
        maintenance_fee_credits: float = config.usage_maintenance_fee_credits
        total_cost_credits: float = provider_cost_credits + maintenance_fee_credits

        record = UsageRecord(
            user_id = self.__di.invoker.id,
            payer_id = payer_id,
            uses_credits = uses_credits,
            is_failed = is_failed,
            chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
            tool = tool,
            tool_purpose = tool_purpose,
            timestamp = datetime.now(timezone.utc),
            model_cost_credits = provider_cost_credits,
            remote_runtime_cost_credits = 0.0,
            api_call_cost_credits = 0.0,
            maintenance_fee_credits = maintenance_fee_credits,
            total_cost_credits = total_cost_credits,
            runtime_seconds = runtime_seconds,
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            total_tokens = total_tokens,
            participant_details = self.__build_participant_details(payer_id),
        )
        return self.__di.usage_record_repo.create(record)

    def track_api_call(
        self,
        tool: ExternalTool,
        tool_purpose: ToolType,
        runtime_seconds: float,
        payer_id: UUID,
        uses_credits: bool,
        is_failed: bool = False,
    ) -> UsageRecord:
        api_call_cost: float = float(tool.cost_estimate.api_call or 0)
        remote_runtime_cost_credits: float = (tool.cost_estimate.second_of_runtime or 0) * runtime_seconds
        maintenance_fee_credits: float = config.usage_maintenance_fee_credits
        total_cost_credits: float = api_call_cost + remote_runtime_cost_credits + maintenance_fee_credits

        record = UsageRecord(
            user_id = self.__di.invoker.id,
            payer_id = payer_id,
            uses_credits = uses_credits,
            is_failed = is_failed,
            chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
            tool = tool,
            tool_purpose = tool_purpose,
            timestamp = datetime.now(timezone.utc),
            model_cost_credits = 0.0,
            remote_runtime_cost_credits = remote_runtime_cost_credits,
            api_call_cost_credits = api_call_cost,
            maintenance_fee_credits = maintenance_fee_credits,
            total_cost_credits = total_cost_credits,
            runtime_seconds = runtime_seconds,
            participant_details = self.__build_participant_details(payer_id),
        )
        return self.__di.usage_record_repo.create(record)

    def __build_participant_details(self, payer_id: UUID) -> ParticipantDetails:
        invoker_info = user_to_participant(self.__di.invoker)
        if payer_id == self.__di.invoker.id:
            return ParticipantDetails(payer = invoker_info, owner = invoker_info)
        payer = self.__di.user_repo.get(payer_id)
        if payer is None:
            payer_info = ParticipantInfo(user_id = payer_id, full_name = None, platform = None, handle = None)
        else:
            payer_info = user_to_participant(payer)
        return ParticipantDetails(
            payer = payer_info,
            owner = user_to_participant(self.__di.invoker),
        )

    def __calculate_llm_cost(
        self,
        cost: CostEstimate,
        input_tokens: int | None,
        output_tokens: int | None,
        search_tokens: int | None,
    ) -> float:
        result = 0.0
        if input_tokens is not None and cost.input_1m_tokens is not None:
            result += (input_tokens / 1_000_000) * cost.input_1m_tokens
        if output_tokens is not None and cost.output_1m_tokens is not None:
            result += (output_tokens / 1_000_000) * cost.output_1m_tokens
        if search_tokens is not None and cost.search_1m_tokens is not None:
            result += (search_tokens / 1_000_000) * cost.search_1m_tokens
        return result

    def __calculate_image_cost(
        self,
        cost: CostEstimate,
        output_image_sizes: list[str] | None,
        input_image_sizes: list[str] | None,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
    ) -> float:
        # when tokens are present, we calculate cost based on tokens using LLM logic
        # because some image models (like the ones from Google AI) report token usage
        if input_tokens is not None or output_tokens is not None or total_tokens is not None:
            return self.__calculate_llm_cost(cost, input_tokens, output_tokens, search_tokens = None)

        # calculate output image cost
        total_cost = 0.0
        if output_image_sizes:
            for output_image_size in output_image_sizes:
                normalized = normalize_image_size_category(output_image_size)
                if normalized == "1k" and cost.output_image_1k:
                    total_cost += float(cost.output_image_1k)
                elif normalized == "2k" and cost.output_image_2k:
                    total_cost += float(cost.output_image_2k)
                elif normalized == "4k" and cost.output_image_4k:
                    total_cost += float(cost.output_image_4k)
                elif cost.output_image_1k:
                    # fallback to 1k if specific size pricing is missing
                    log.w(f"No pricing for output image size '{output_image_size}', using 1K pricing")
                    total_cost += float(cost.output_image_1k)

        # calculate input image cost
        if input_image_sizes:
            for input_image_size in input_image_sizes:
                normalized = normalize_image_size_category(input_image_size)
                if normalized == "1k" and cost.input_image_1k:
                    total_cost += float(cost.input_image_1k)
                elif normalized == "2k" and cost.input_image_2k:
                    total_cost += float(cost.input_image_2k)
                elif normalized == "4k" and cost.input_image_4k:
                    total_cost += float(cost.input_image_4k)
                elif normalized == "8k" and cost.input_image_8k:
                    total_cost += float(cost.input_image_8k)
                elif normalized == "12k" and cost.input_image_12k:
                    total_cost += float(cost.input_image_12k)
                elif cost.input_image_1k:
                    # fallback to 1k if specific size pricing is missing
                    log.w(f"No pricing for input image size '{input_image_size}', using 1K pricing")
                    total_cost += float(cost.input_image_1k)

        if total_cost > 0:
            return total_cost

        log.e(
            f"Cannot calculate cost for image: no token usage and no pricing for sizes "
            f"(output: {output_image_sizes}, input: {input_image_sizes})",
        )
        return 0.0
