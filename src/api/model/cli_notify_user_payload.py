from pydantic import BaseModel


class CliNotifyUserPayload(BaseModel):
    message: str
    platform: str | None = None
