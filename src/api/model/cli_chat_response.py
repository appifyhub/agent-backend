from pydantic import BaseModel


class CliChatResponse(BaseModel):
    chat_id: str
    platform: str
    title: str | None = None
    is_private: bool
