from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from db.model.user import UserDB
from features.users.user import User
from features.users.user_mapper import apply_to_db_model, db, domain
from features.users.user_remote_data import UserRemoteData
from util.error_codes import USER_NOT_FOUND
from util.errors import NotFoundError


class UserRepository:

    _db: Session

    def __init__(self, db_session: Session):
        self._db = db_session

    def get(self, user_id: UUID) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.id == user_id,
        ).first()
        return domain(db_model)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        db_models = self._db.query(UserDB).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models if db_model is not None]

    def count(self) -> int:
        return self._db.query(UserDB).count()

    def get_by_telegram_user_id(self, telegram_user_id: int) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.telegram_user_id == telegram_user_id,
        ).first()
        return domain(db_model)

    def get_by_telegram_username(self, telegram_username: str) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.telegram_username == telegram_username,
        ).first()
        return domain(db_model)

    def get_by_whatsapp_user_id(self, whatsapp_user_id: str) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.whatsapp_user_id == whatsapp_user_id,
        ).first()
        return domain(db_model)

    def get_by_whatsapp_phone_number(self, whatsapp_phone_number: str) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.whatsapp_phone_number == whatsapp_phone_number,
        ).first()
        return domain(db_model)

    def get_by_connect_key(self, connect_key: str) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.connect_key == connect_key,
        ).first()
        return domain(db_model)

    def get_by_remote_data(self, remote_data: UserRemoteData) -> User | None:
        if remote_data.telegram_user_id is not None:
            user = self.get_by_telegram_user_id(remote_data.telegram_user_id)
            if user is not None:
                return user
        if remote_data.telegram_username:
            user = self.get_by_telegram_username(remote_data.telegram_username)
            if user is not None:
                return user
        if remote_data.whatsapp_user_id:
            user = self.get_by_whatsapp_user_id(remote_data.whatsapp_user_id)
            if user is not None:
                return user
        if remote_data.whatsapp_phone_number:
            return self.get_by_whatsapp_phone_number(remote_data.whatsapp_phone_number.get_secret_value())
        return None

    def save(self, user: User, commit: bool = True) -> User:
        existing: UserDB | None = None
        if user.id is not None:
            existing = self._db.query(UserDB).filter(
                UserDB.id == user.id,
            ).first()

        if existing is not None:
            apply_to_db_model(user, existing)
            self._db.flush()
            if commit:
                self._db.commit()
            self._db.refresh(existing)
            return domain(existing)

        db_model = db(user)
        self._db.add(db_model)
        self._db.flush()
        if commit:
            self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def update_locked(self, user_id: UUID, update_fn: Callable[[User], User]) -> User:
        db_model = self._db.query(UserDB).filter(
            UserDB.id == user_id,
        ).with_for_update().first()
        if db_model is None:
            raise NotFoundError(f"User {user_id} not found", USER_NOT_FOUND)

        updated = update_fn(domain(db_model))
        apply_to_db_model(updated, db_model)
        self._db.commit()
        self._db.refresh(db_model)
        return domain(db_model)

    def update_locked_pair(
        self,
        first_id: UUID,
        second_id: UUID,
        update_fn: Callable[[User, User], tuple[User, User]],
    ) -> tuple[User, User]:
        # rows are locked in UUID order to avoid deadlocks
        lock_order = sorted([first_id, second_id])

        first = self._db.query(UserDB).filter(
            UserDB.id == lock_order[0],
        ).with_for_update().first()
        second = self._db.query(UserDB).filter(
            UserDB.id == lock_order[1],
        ).with_for_update().first()

        if first is None or second is None:
            raise NotFoundError("User not found", USER_NOT_FOUND)

        # locks might have come out of order, but callbacks receive caller order; let's check which is which
        mapped_first = first if first.id == first_id else second
        mapped_second = second if second.id == second_id else first

        updated_first, updated_second = update_fn(domain(mapped_first), domain(mapped_second))
        apply_to_db_model(updated_first, mapped_first)
        apply_to_db_model(updated_second, mapped_second)

        self._db.commit()
        self._db.refresh(mapped_first)
        self._db.refresh(mapped_second)
        return domain(mapped_first), domain(mapped_second)

    def delete(self, user_id: UUID, commit: bool = True) -> User | None:
        db_model = self._db.query(UserDB).filter(
            UserDB.id == user_id,
        ).first()
        if db_model is None:
            return None
        snapshot = domain(db_model)
        self._db.delete(db_model)
        self._db.flush()
        if commit:
            self._db.commit()
        return snapshot
