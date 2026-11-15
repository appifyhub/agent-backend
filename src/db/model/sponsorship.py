from sqlalchemy import DateTime, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.model.base import BaseModel, Column


class SponsorshipDB(BaseModel):
    __tablename__ = "sponsorships"

    sponsor_id = Column(UUID(as_uuid = True), nullable = False)
    receiver_id = Column(UUID(as_uuid = True), nullable = False)
    sponsored_at = Column(DateTime, default = func.now(), nullable = False)
    accepted_at = Column(DateTime, nullable = True)

    __table_args__ = (
        PrimaryKeyConstraint(sponsor_id, receiver_id, name = "pk_sponsorships"),
        ForeignKeyConstraint([sponsor_id], ["simulants.id"], name = "sponsorships_sponsor_id_fkey"),
        ForeignKeyConstraint([receiver_id], ["simulants.id"], name = "sponsorships_receiver_id_fkey"),
    )
