import secrets
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from pydantic import SecretStr

from db.model.user import UserDB


def generate_connect_key() -> str:
    allowed_chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    key_chars = [secrets.choice(allowed_chars) for _ in range(12)]
    return f"{''.join(key_chars[0:4])}-{''.join(key_chars[4:8])}-{''.join(key_chars[8:12])}"


@dataclass(kw_only = True)
class User:

    id: UUID | None = None
    created_at: date | None = None

    full_name: str | None = None
    about_me: SecretStr | None = None
    custom_prompt: SecretStr | None = None

    telegram_username: str | None = None
    telegram_chat_id: str | None = None
    telegram_user_id: int | None = None

    whatsapp_user_id: str | None = None
    whatsapp_phone_number: SecretStr | None = None

    open_ai_key: SecretStr | None = None
    anthropic_key: SecretStr | None = None
    google_ai_key: SecretStr | None = None
    perplexity_key: SecretStr | None = None
    replicate_key: SecretStr | None = None
    rapid_api_key: SecretStr | None = None
    coinmarketcap_key: SecretStr | None = None
    twelve_data_api_key: SecretStr | None = None
    x_key: SecretStr | None = None
    x_ai_key: SecretStr | None = None

    tool_choice_chat: str | None = None
    tool_choice_reasoning: str | None = None
    tool_choice_copywriting: str | None = None
    tool_choice_vision: str | None = None
    tool_choice_hearing: str | None = None
    tool_choice_images_gen: str | None = None
    tool_choice_images_edit: str | None = None
    tool_choice_search: str | None = None
    tool_choice_embedding: str | None = None
    tool_choice_api_fiat_exchange: str | None = None
    tool_choice_api_crypto_exchange: str | None = None
    tool_choice_api_stock_quote: str | None = None
    tool_choice_api_twitter: str | None = None

    credit_balance: float = 0.0

    is_on_waitlist: bool = False
    is_invited_to_start: bool = False
    are_policies_accepted: bool = False

    connect_key: str = field(default_factory = generate_connect_key)
    group: UserDB.Group = UserDB.Group.standard

    def has_any_api_key(self) -> bool:
        return any([
            self.open_ai_key,
            self.anthropic_key,
            self.google_ai_key,
            self.perplexity_key,
            self.replicate_key,
            self.rapid_api_key,
            self.coinmarketcap_key,
            self.twelve_data_api_key,
            self.x_key,
            self.x_ai_key,
        ])
