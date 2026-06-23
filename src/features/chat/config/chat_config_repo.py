from uuid import UUID

from sqlalchemy.orm import Session

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData


class ChatConfigRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, chat_id: UUID) -> ChatConfig | None:
        db_model = self._db.query(ChatConfigDB).filter(
            ChatConfigDB.chat_id == chat_id,
        ).first()
        return domain(db_model)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ChatConfig]:
        db_models = self._db.query(ChatConfigDB).offset(skip).limit(limit).all()
        return [domain(m) for m in db_models if m is not None]

    def get_by_external_identifiers(
        self,
        external_id: str,
        chat_type: ChatConfigDB.ChatType,
    ) -> ChatConfig | None:
        db_model = self._db.query(ChatConfigDB).filter(
            ChatConfigDB.external_id == external_id,
            ChatConfigDB.chat_type == chat_type,
        ).first()
        return domain(db_model)

    def save(self, chat_config: ChatConfig | ChatConfigRemoteData) -> ChatConfig:
        if isinstance(chat_config, ChatConfigRemoteData):
            return self.__save_remote_data(chat_config)
        return self.__save_chat_config(chat_config)

    def delete(self, chat_id: UUID) -> ChatConfig | None:
        db_model = self._db.query(ChatConfigDB).filter(
            ChatConfigDB.chat_id == chat_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.commit()
        return snapshot

    def __save_remote_data(self, remote_data: ChatConfigRemoteData) -> ChatConfig:
        existing = self.get_by_external_identifiers(
            external_id = remote_data.external_id,
            chat_type = remote_data.chat_type,
        )
        if existing is not None:
            return self.__save_chat_config(apply_remote_data(existing, remote_data))
        return self.__save_chat_config(from_remote_data(remote_data))

    def __save_chat_config(self, chat_config: ChatConfig) -> ChatConfig:
        existing: ChatConfigDB | None = None
        if chat_config.chat_id is not None:
            existing = self._db.query(ChatConfigDB).filter(
                ChatConfigDB.chat_id == chat_config.chat_id,
            ).first()

        if existing is not None:
            apply_to_db_model(chat_config, existing)
            self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(chat_config)
        self._db.add(db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)
