from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(kw_only = True)
class UserRemoteData:
    full_name: str | None = None

    telegram_username: str | None = None
    telegram_chat_id: str | None = None
    telegram_user_id: int | None = None

    whatsapp_user_id: str | None = None
    whatsapp_phone_number: SecretStr | None = None
