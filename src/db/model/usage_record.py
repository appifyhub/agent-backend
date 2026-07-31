import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.model.base import BaseModel


class UsageRecordDB(BaseModel):
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid = True), primary_key = True, default = uuid.uuid4)

    # core properties
    user_id = Column(UUID(as_uuid = True), nullable = False)
    payer_id = Column(UUID(as_uuid = True), nullable = False)
    uses_credits = Column(Boolean, nullable = False, server_default = "false")
    is_failed = Column(Boolean, nullable = False, server_default = "false")
    chat_id = Column(UUID(as_uuid = True), nullable = True)
    tool_id = Column(String, nullable = False)
    tool_name = Column(String, nullable = False)
    provider_id = Column(String, nullable = False)
    provider_name = Column(String, nullable = False)
    purpose = Column(String, nullable = False)
    timestamp = Column(DateTime, default = func.now(), nullable = False)
    runtime_seconds = Column(Float, nullable = False)
    remote_runtime_seconds = Column(Float, nullable = True)

    # cost properties
    model_cost_credits = Column(Float, nullable = False)
    remote_runtime_cost_credits = Column(Float, nullable = False)
    api_call_cost_credits = Column(Float, nullable = False)
    maintenance_fee_credits = Column(Float, nullable = False)
    total_cost_credits = Column(Float, nullable = False)

    # token-based properties
    input_tokens = Column(Integer, nullable = True)
    output_tokens = Column(Integer, nullable = True)
    search_tokens = Column(Integer, nullable = True)
    total_tokens = Column(Integer, nullable = True)

    # image-related properties
    output_image_sizes = Column(JSON, nullable = True)
    input_image_sizes = Column(JSON, nullable = True)
    # video-related properties
    output_video_size = Column(String, nullable = True)
    output_video_duration_seconds = Column(Float, nullable = True)

    # transfer-related properties
    counterpart_id = Column(UUID(as_uuid = True), nullable = True)
    note = Column(String, nullable = True)

    # participant snapshot properties
    participant_details = Column(JSON, nullable = True)

    __table_args__ = (
        Index("idx_usage_records_user_timestamp", user_id, timestamp.desc()),
        Index("idx_usage_records_counterpart_timestamp", counterpart_id, timestamp.desc()),
    )
