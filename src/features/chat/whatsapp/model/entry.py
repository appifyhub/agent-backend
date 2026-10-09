from pydantic import BaseModel

from features.chat.whatsapp.model.change import Change


class Entry(BaseModel):
    """https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/reference/messages"""
    id: str
    changes: list[Change] | None = None
