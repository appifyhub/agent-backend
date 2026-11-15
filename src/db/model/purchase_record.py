import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from db.model.base import BaseModel, Column


class PurchaseRecordDB(BaseModel):
    __tablename__ = "purchase_records"

    id = Column(UUID(as_uuid = True), primary_key = True, default = uuid.uuid4)
    user_id = Column(UUID(as_uuid = True), nullable = True)
    seller_id = Column(String, nullable = False)
    sale_id = Column(String, nullable = False, unique = True)
    sale_timestamp = Column(DateTime, nullable = False)
    price = Column(Integer, nullable = False)
    product_id = Column(String, nullable = False)
    product_name = Column(String, nullable = False)
    product_permalink = Column(String, nullable = False)
    short_product_id = Column(String, nullable = False)
    license_key = Column(String, nullable = True)
    quantity = Column(Integer, nullable = False)
    gumroad_fee = Column(Integer, nullable = False, default = 0)
    affiliate_credit_amount_cents = Column(Integer, nullable = False, default = 0)
    discover_fee_charge = Column(Boolean, nullable = False, default = False)
    url_params = Column(JSON, nullable = True)
    custom_fields = Column(JSON, nullable = True)
    test = Column(Boolean, nullable = False, default = False)
    is_preorder_authorization = Column(Boolean, nullable = False, default = False)
    refunded = Column(Boolean, nullable = False, default = False)

    __table_args__ = (
        ForeignKeyConstraint([user_id], ["simulants.id"], name = "purchase_records_user_id_fkey"),
        Index("idx_purchase_records_user_timestamp", user_id, sale_timestamp.desc()),
        Index("idx_purchase_records_license_key", license_key),
    )
