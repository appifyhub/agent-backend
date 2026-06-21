from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from db.model.price_alert import PriceAlertDB
from features.currencies.price_alert import PriceAlert
from features.currencies.price_alert_mapper import db, domain


class PriceAlertRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(
        self,
        chat_id: UUID,
        base_currency: str,
        desired_currency: str,
    ) -> PriceAlert | None:
        db_model = self._db.query(PriceAlertDB).filter(
            PriceAlertDB.chat_id == chat_id,
            PriceAlertDB.base_currency == base_currency,
            PriceAlertDB.desired_currency == desired_currency,
        ).first()
        return domain(db_model)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PriceAlert]:
        db_models = self._db.query(PriceAlertDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def get_all_by_chat(self, chat_id: UUID) -> list[PriceAlert]:
        db_models = self._db.query(PriceAlertDB).filter(
            PriceAlertDB.chat_id == chat_id,
        ).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def save(self, price_alert: PriceAlert) -> PriceAlert:
        existing = self._db.query(PriceAlertDB).filter(
            PriceAlertDB.chat_id == price_alert.chat_id,
            PriceAlertDB.base_currency == price_alert.base_currency,
            PriceAlertDB.desired_currency == price_alert.desired_currency,
        ).first()
        if existing is not None:
            self.__copy_to_db_model(price_alert, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(price_alert)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(
        self,
        chat_id: UUID,
        base_currency: str,
        desired_currency: str,
    ) -> PriceAlert | None:
        db_model = self._db.query(PriceAlertDB).filter(
            PriceAlertDB.chat_id == chat_id,
            PriceAlertDB.base_currency == base_currency,
            PriceAlertDB.desired_currency == desired_currency,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_stale(self, cutoff: datetime) -> int:
        deleted_count = self._db.query(PriceAlertDB).filter(
            PriceAlertDB.last_price_time < cutoff,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def __copy_to_db_model(self, source: PriceAlert, target: PriceAlertDB):
        target.owner_id = source.owner_id
        target.threshold_percent = source.threshold_percent
        target.last_price = source.last_price
        target.last_price_time = source.last_price_time
