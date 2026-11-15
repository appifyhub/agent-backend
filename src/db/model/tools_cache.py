from sqlalchemy import DateTime, String, Text

from db.model.base import BaseModel, Column


class ToolsCacheDB(BaseModel):
    __tablename__ = "tools_cache"

    key = Column(String, primary_key = True)
    value = Column(Text, nullable = False)
    created_at = Column(DateTime, nullable = False)
    expires_at = Column(DateTime, nullable = True)
