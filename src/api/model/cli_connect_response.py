from datetime import datetime

from pydantic import BaseModel


class CliConnectResponse(BaseModel):
    token: str
    expires_at: datetime
    user_id: str
    user_display_name: str
    credit_balance: float
