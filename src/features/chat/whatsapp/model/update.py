from pydantic import BaseModel, ConfigDict

from features.chat.whatsapp.model.entry import Entry


class Update(BaseModel):
    """Slim WhatsApp webhook envelope.

    Matches the documented webhook root: { object: str, entry: [Entry] }.
    Extra fields are ignored to keep parsing resilient to API changes.
    """

    model_config = ConfigDict(extra = "ignore")

    object: str
    entry: list[Entry] | None = None
