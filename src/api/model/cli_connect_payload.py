from pydantic import BaseModel


class CliConnectPayload(BaseModel):
    connect_key: str
    ttl_as_text: str | None = None
    device_id: str
    hostname: str
    os: str
