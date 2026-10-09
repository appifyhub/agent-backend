from pydantic import BaseModel


class StatusPricing(BaseModel):
    billable: bool | None = None
    type: str | None = None
    category: str | None = None


class MessageStatus(BaseModel):
    """https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status"""

    id: str
    status: str
    timestamp: str
    recipient_id: str
    recipient_type: str | None = None
    recipient_participant_id: str | None = None
    pricing: StatusPricing | None = None
