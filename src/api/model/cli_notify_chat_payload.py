from pydantic import BaseModel


class CliNotifyChatPayload(BaseModel):
    message: str
