from pydantic import BaseModel


class CliNotifyResponse(BaseModel):
    chat_id: str
    platform: str
    title: str | None = None
    is_private: bool
    credit_balance: float
