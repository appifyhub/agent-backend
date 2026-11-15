import uuid
from enum import Enum

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy import Enum as EnumSQL
from sqlalchemy.dialects.postgresql import UUID

from db.model.base import BaseModel, Column


class ChatConfigDB(BaseModel):
    __tablename__ = "chat_configs"

    class MediaMode(Enum):
        photo = "photo"
        file = "file"
        all = "all"

        @classmethod
        def lookup(cls, value) -> "ChatConfigDB.MediaMode | None":
            try:
                return cls(value)
            except ValueError:
                return None

        def __lt__(self, other):
            if not isinstance(other, ChatConfigDB.MediaMode):
                return NotImplemented
            hierarchy = {
                "photo": 1,
                "file": 2,
                "all": 3,
            }
            return hierarchy[self.value] < hierarchy[other.value]

        def __ge__(self, other):
            if not isinstance(other, ChatConfigDB.MediaMode):
                return NotImplemented
            hierarchy = {
                "photo": 1,
                "file": 2,
                "all": 3,
            }
            return hierarchy[self.value] >= hierarchy[other.value]

    class ReleaseNotifications(Enum):
        none = "none"
        major = "major"
        minor = "minor"
        all = "all"

        @classmethod
        def lookup(cls, value) -> "ChatConfigDB.ReleaseNotifications | None":
            try:
                return cls(value)
            except ValueError:
                return None

        def __lt__(self, other):
            if not isinstance(other, ChatConfigDB.ReleaseNotifications):
                return NotImplemented
            hierarchy = {
                "none": 1,
                "major": 2,
                "minor": 3,
                "all": 4,
            }
            return hierarchy[self.value] < hierarchy[other.value]

        def __ge__(self, other):
            if not isinstance(other, ChatConfigDB.ReleaseNotifications):
                return NotImplemented
            hierarchy = {
                "none": 1,
                "major": 2,
                "minor": 3,
                "all": 4,
            }
            return hierarchy[self.value] >= hierarchy[other.value]

    class ChatType(Enum):
        telegram = "telegram"
        whatsapp = "whatsapp"
        github = "github"
        background = "background"

        @classmethod
        def lookup(cls, value) -> "ChatConfigDB.ChatType | None":
            try:
                return cls(value)
            except ValueError:
                return None

        def __lt__(self, other):
            if not isinstance(other, ChatConfigDB.ChatType):
                return NotImplemented
            hierarchy = {
                "telegram": 1,
                "whatsapp": 2,
                "github": 3,
                "background": 4,
            }
            return hierarchy[self.value] < hierarchy[other.value]

        def __ge__(self, other):
            if not isinstance(other, ChatConfigDB.ChatType):
                return NotImplemented
            hierarchy = {
                "telegram": 1,
                "whatsapp": 2,
                "github": 3,
                "background": 4,
            }
            return hierarchy[self.value] >= hierarchy[other.value]

    chat_id = Column(UUID(as_uuid = True), primary_key = True, default = uuid.uuid4)
    external_id = Column(String, nullable = True)
    language_iso_code = Column(String, nullable = True)
    language_name = Column(String, nullable = True)
    title = Column(String, nullable = True)
    is_private = Column(Boolean, nullable = False)
    reply_chance_percent = Column(Integer, nullable = False)
    release_notifications = Column(EnumSQL(ReleaseNotifications), nullable = False, default = ReleaseNotifications.major)
    media_mode = Column(EnumSQL(MediaMode), nullable = False, default = MediaMode.photo)
    chat_type = Column(EnumSQL(ChatType), nullable = False)

    __table_args__ = (
        Index(
            "uq_chat_configs_external_id_type",
            external_id,
            chat_type,
            unique = True,
            postgresql_where = external_id.isnot(None),
        ),
    )
