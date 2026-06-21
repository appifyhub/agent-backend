from datetime import datetime

from sqlalchemy.orm import Session

from db.model.tools_cache import ToolsCacheDB
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_mapper import db, domain


class ToolsCacheRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, key: str) -> ToolsCache | None:
        return domain(self._get_db_model(key))

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ToolsCache]:
        db_models = self._db.query(ToolsCacheDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def save(self, tools_cache: ToolsCache) -> ToolsCache:
        existing = self._get_db_model(tools_cache.key)
        if existing is not None:
            self.__copy_to_db_model(tools_cache, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(tools_cache)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def delete(self, key: str) -> ToolsCache | None:
        db_model = self._get_db_model(key)
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def delete_expired(self) -> int:
        deleted_count = self._db.query(ToolsCacheDB).filter(
            ToolsCacheDB.expires_at < datetime.now(),
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted_count

    def _get_db_model(self, key: str) -> ToolsCacheDB | None:
        return self._db.query(ToolsCacheDB).filter(
            ToolsCacheDB.key == key,
        ).first()

    def __copy_to_db_model(self, source: ToolsCache, target: ToolsCacheDB):
        target.value = source.value
        target.created_at = source.created_at
        target.expires_at = source.expires_at
