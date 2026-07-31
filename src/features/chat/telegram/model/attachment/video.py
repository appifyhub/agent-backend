from pydantic import BaseModel


class Video(BaseModel):
    """https://core.telegram.org/bots/api#video"""
    file_id: str
    file_unique_id: str
    width: int
    height: int
    duration: int
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
