import base64
from dataclasses import dataclass, field
from datetime import datetime

from util.functions import digest_md5

KEY_DELIMITER = "~"


@dataclass(kw_only = True)
class ToolsCache:
    key: str
    value: str
    created_at: datetime = field(default_factory = datetime.now)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.now()

    @staticmethod
    def create_key(prefix: str, identifier: str) -> str:
        prefix_b64 = base64.b64encode(prefix.encode()).decode()
        identifier_b64 = base64.b64encode(identifier.encode()).decode()
        return digest_md5(f"{prefix_b64}{KEY_DELIMITER}{identifier_b64}")
