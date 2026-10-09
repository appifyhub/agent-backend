from pydantic import BaseModel

from features.chat.whatsapp.model.contact import Contact
from features.chat.whatsapp.model.message import Message
from features.chat.whatsapp.model.metadata import Metadata
from features.chat.whatsapp.model.status import MessageStatus


class Value(BaseModel):
    """https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/reference/messages"""
    messaging_product: str
    metadata: Metadata
    contacts: list[Contact] | None = None
    messages: list[Message] | None = None
    statuses: list[MessageStatus] | None = None
