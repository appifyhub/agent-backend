from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from db.model.sponsorship import SponsorshipDB
from features.sponsorships.sponsorship import Sponsorship
from features.sponsorships.sponsorship_mapper import db, domain


class SponsorshipRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, sponsor_id: UUID, receiver_id: UUID) -> Sponsorship | None:
        db_model = self._get_db_model(sponsor_id, receiver_id)
        return domain(db_model)

    def get_all_by_sponsor(
        self,
        sponsor_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Sponsorship]:
        db_models = self._db.query(SponsorshipDB).filter(
            SponsorshipDB.sponsor_id == sponsor_id,
        ).offset(skip).limit(limit).all()
        return [domain(m) for m in db_models if m is not None]

    def get_all_by_receiver(
        self,
        receiver_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Sponsorship]:
        db_models = self._db.query(SponsorshipDB).filter(
            SponsorshipDB.receiver_id == receiver_id,
        ).offset(skip).limit(limit).all()
        return [domain(m) for m in db_models if m is not None]

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Sponsorship]:
        db_models = self._db.query(SponsorshipDB).offset(skip).limit(limit).all()
        return [domain(m) for m in db_models if m is not None]

    def save(self, sponsorship: Sponsorship) -> Sponsorship:
        existing = self._get_db_model(sponsorship.sponsor_id, sponsorship.receiver_id)
        if existing is not None:
            self.__copy_to_db_model(sponsorship, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(sponsorship)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(self, sponsor_id: UUID, receiver_id: UUID) -> Sponsorship | None:
        db_model = self._get_db_model(sponsor_id, receiver_id)
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_all_by_receiver(self, receiver_id: UUID) -> int:
        deleted_count = self._db.query(SponsorshipDB).filter(
            SponsorshipDB.receiver_id == receiver_id,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def delete_unaccepted_older_than(self, cutoff: datetime) -> int:
        deleted_count = self._db.query(SponsorshipDB).filter(
            SponsorshipDB.accepted_at.is_(None),
            SponsorshipDB.sponsored_at < cutoff,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def _get_db_model(self, sponsor_id: UUID, receiver_id: UUID) -> SponsorshipDB | None:
        return self._db.query(SponsorshipDB).filter(
            SponsorshipDB.sponsor_id == sponsor_id,
            SponsorshipDB.receiver_id == receiver_id,
        ).first()

    def __copy_to_db_model(self, source: Sponsorship, target: SponsorshipDB):
        target.sponsored_at = source.sponsored_at
        target.accepted_at = source.accepted_at
