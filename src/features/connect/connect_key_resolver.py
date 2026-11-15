from sqlalchemy.orm import Session

from di.di import DI
from features.users.user import User
from util.error_codes import CONNECT_KEY_NOT_FOUND
from util.errors import NotFoundError


def require_user_by_connect_key(connect_key: str, db: Session) -> User:
    user = DI(db).user_repo.get_by_connect_key(connect_key.strip().upper())
    if user is None:
        raise NotFoundError("Connect key not found", CONNECT_KEY_NOT_FOUND)
    return user
