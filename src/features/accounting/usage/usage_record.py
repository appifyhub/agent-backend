from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from features.accounting.usage.participant_details import ParticipantDetails
from features.external_tools.external_tool import ExternalTool, ToolType


@dataclass(kw_only = True)
class UsageRecord:
    # core properties
    user_id: UUID
    payer_id: UUID
    uses_credits: bool = False
    is_failed: bool = False
    chat_id: UUID | None = None
    tool: ExternalTool
    tool_purpose: ToolType
    timestamp: datetime = field(default_factory = lambda: datetime.now(timezone.utc))
    runtime_seconds: float
    remote_runtime_seconds: float | None = None
    # cost properties
    model_cost_credits: float
    remote_runtime_cost_credits: float
    api_call_cost_credits: float
    maintenance_fee_credits: float
    total_cost_credits: float
    # token-based properties
    input_tokens: int | None = None
    output_tokens: int | None = None
    search_tokens: int | None = None
    total_tokens: int | None = None
    # image-related properties
    output_image_sizes: list[str] | None = None
    input_image_sizes: list[str] | None = None
    # video-related properties
    output_video_size: str | None = None
    output_video_duration_seconds: float | None = None
    # transfer-related properties
    counterpart_id: UUID | None = None
    note: str | None = None
    # participant snapshot properties
    participant_details: ParticipantDetails | None = None
