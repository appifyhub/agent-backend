from sqlalchemy import Column, DateTime, Float, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from db.model.base import BaseModel


class PriceAlertDB(BaseModel):
    __tablename__ = "price_alerts"

    chat_id = Column(UUID(as_uuid = True), nullable = False)
    owner_id = Column(UUID(as_uuid = True), nullable = False)
    asset_type = Column(String, nullable = False)
    asset_id = Column(String, nullable = False)
    currency = Column(String, nullable = False)
    threshold_percent = Column(Integer, nullable = False)
    last_price = Column(Float, nullable = False)
    last_price_time = Column(DateTime, nullable = False)

    __table_args__ = (
        PrimaryKeyConstraint(chat_id, asset_type, asset_id, currency, name = "pk_price_alert"),
        ForeignKeyConstraint([chat_id], ["chat_configs.chat_id"], name = "price_alerts_chat_id_fkey"),
        ForeignKeyConstraint([owner_id], ["simulants.id"], name = "price_alerts_owner_id_fkey"),
    )
