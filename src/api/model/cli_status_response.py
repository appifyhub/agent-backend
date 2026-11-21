from pydantic import BaseModel


class CliStatusResponse(BaseModel):
    status: str
    service_version: str
    cli_version: str | None = None
