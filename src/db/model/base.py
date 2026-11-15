from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import declarative_base

# at runtime this is SQLAlchemy's Column; type checkers see Any, because they would otherwise
# infer Column[T] for instance attributes and reject every assignment of a plain value
if TYPE_CHECKING:
    Column: Any
else:
    from sqlalchemy import Column  # noqa: F401

BaseModel = declarative_base()
