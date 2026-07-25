from pydantic import BaseModel


class UserSettingsResponse(BaseModel):
    id: str
    created_at: str

    full_name: str | None = None
    about_me: str | None = None
    custom_prompt: str | None = None

    telegram_username: str | None = None
    telegram_chat_id: str | None = None
    telegram_user_id: int | None = None

    whatsapp_user_id: str | None = None
    whatsapp_phone_number: str | None = None

    open_ai_key: str | None = None
    anthropic_key: str | None = None
    google_ai_key: str | None = None
    perplexity_key: str | None = None
    replicate_key: str | None = None
    rapid_api_key: str | None = None
    coinmarketcap_key: str | None = None
    twelve_data_api_key: str | None = None
    x_key: str | None = None
    x_ai_key: str | None = None

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

    credit_balance: float
    is_on_waitlist: bool
    is_invited_to_start: bool
    are_policies_accepted: bool
    is_sponsored: bool

    group: str
