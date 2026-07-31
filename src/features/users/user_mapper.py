from dataclasses import replace

from pydantic import SecretStr

from db.model.user import UserDB
from features.users.user import User
from features.users.user_remote_data import UserRemoteData


def _secret(value: str | SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value
    return SecretStr(value)


def _secret_value(value: SecretStr | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def domain(db_model: UserDB | None) -> User | None:
    if db_model is None:
        return None

    return User(
        id = db_model.id,
        created_at = db_model.created_at,

        full_name = db_model.full_name,
        about_me = _secret(db_model.about_me),
        custom_prompt = _secret(db_model.custom_prompt),

        telegram_username = db_model.telegram_username,
        telegram_chat_id = db_model.telegram_chat_id,
        telegram_user_id = db_model.telegram_user_id,

        whatsapp_user_id = db_model.whatsapp_user_id,
        whatsapp_phone_number = _secret(db_model.whatsapp_phone_number),

        open_ai_key = _secret(db_model.open_ai_key),
        anthropic_key = _secret(db_model.anthropic_key),
        google_ai_key = _secret(db_model.google_ai_key),
        perplexity_key = _secret(db_model.perplexity_key),
        replicate_key = _secret(db_model.replicate_key),
        rapid_api_key = _secret(db_model.rapid_api_key),
        coinmarketcap_key = _secret(db_model.coinmarketcap_key),
        twelve_data_api_key = _secret(db_model.twelve_data_api_key),
        x_key = _secret(db_model.x_key),
        x_ai_key = _secret(db_model.x_ai_key),

        tool_choice_chat = db_model.tool_choice_chat,
        tool_choice_reasoning = db_model.tool_choice_reasoning,
        tool_choice_copywriting = db_model.tool_choice_copywriting,
        tool_choice_vision = db_model.tool_choice_vision,
        tool_choice_hearing = db_model.tool_choice_hearing,
        tool_choice_images_gen = db_model.tool_choice_images_gen,
        tool_choice_videos_gen = db_model.tool_choice_videos_gen,
        tool_choice_images_edit = db_model.tool_choice_images_edit,
        tool_choice_search = db_model.tool_choice_search,
        tool_choice_embedding = db_model.tool_choice_embedding,
        tool_choice_api_fiat_exchange = db_model.tool_choice_api_fiat_exchange,
        tool_choice_api_crypto_exchange = db_model.tool_choice_api_crypto_exchange,
        tool_choice_api_stock_quote = db_model.tool_choice_api_stock_quote,
        tool_choice_api_twitter = db_model.tool_choice_api_twitter,

        credit_balance = db_model.credit_balance,

        is_on_waitlist = db_model.is_on_waitlist,
        is_invited_to_start = db_model.is_invited_to_start,
        are_policies_accepted = db_model.are_policies_accepted,

        connect_key = db_model.connect_key,
        group = db_model.group,
    )


def db(domain_model: User | None) -> UserDB | None:
    if domain_model is None:
        return None

    return UserDB(
        id = domain_model.id,
        created_at = domain_model.created_at,

        full_name = domain_model.full_name,
        about_me = _secret_value(domain_model.about_me),
        custom_prompt = _secret_value(domain_model.custom_prompt),

        telegram_username = domain_model.telegram_username,
        telegram_chat_id = domain_model.telegram_chat_id,
        telegram_user_id = domain_model.telegram_user_id,

        whatsapp_user_id = domain_model.whatsapp_user_id,
        whatsapp_phone_number = _secret_value(domain_model.whatsapp_phone_number),

        open_ai_key = _secret_value(domain_model.open_ai_key),
        anthropic_key = _secret_value(domain_model.anthropic_key),
        google_ai_key = _secret_value(domain_model.google_ai_key),
        perplexity_key = _secret_value(domain_model.perplexity_key),
        replicate_key = _secret_value(domain_model.replicate_key),
        rapid_api_key = _secret_value(domain_model.rapid_api_key),
        coinmarketcap_key = _secret_value(domain_model.coinmarketcap_key),
        twelve_data_api_key = _secret_value(domain_model.twelve_data_api_key),
        x_key = _secret_value(domain_model.x_key),
        x_ai_key = _secret_value(domain_model.x_ai_key),

        tool_choice_chat = domain_model.tool_choice_chat,
        tool_choice_reasoning = domain_model.tool_choice_reasoning,
        tool_choice_copywriting = domain_model.tool_choice_copywriting,
        tool_choice_vision = domain_model.tool_choice_vision,
        tool_choice_hearing = domain_model.tool_choice_hearing,
        tool_choice_images_gen = domain_model.tool_choice_images_gen,
        tool_choice_videos_gen = domain_model.tool_choice_videos_gen,
        tool_choice_images_edit = domain_model.tool_choice_images_edit,
        tool_choice_search = domain_model.tool_choice_search,
        tool_choice_embedding = domain_model.tool_choice_embedding,
        tool_choice_api_fiat_exchange = domain_model.tool_choice_api_fiat_exchange,
        tool_choice_api_crypto_exchange = domain_model.tool_choice_api_crypto_exchange,
        tool_choice_api_stock_quote = domain_model.tool_choice_api_stock_quote,
        tool_choice_api_twitter = domain_model.tool_choice_api_twitter,

        credit_balance = domain_model.credit_balance,

        is_on_waitlist = domain_model.is_on_waitlist,
        is_invited_to_start = domain_model.is_invited_to_start,
        are_policies_accepted = domain_model.are_policies_accepted,

        connect_key = domain_model.connect_key,
        group = domain_model.group,
    )


def apply_to_db_model(
    domain_model: User,
    db_model: UserDB,
) -> None:
    db_model.full_name = domain_model.full_name
    db_model.about_me = _secret_value(domain_model.about_me)
    db_model.custom_prompt = _secret_value(domain_model.custom_prompt)

    db_model.telegram_username = domain_model.telegram_username
    db_model.telegram_chat_id = domain_model.telegram_chat_id
    db_model.telegram_user_id = domain_model.telegram_user_id

    db_model.whatsapp_user_id = domain_model.whatsapp_user_id
    db_model.whatsapp_phone_number = _secret_value(domain_model.whatsapp_phone_number)

    db_model.open_ai_key = _secret_value(domain_model.open_ai_key)
    db_model.anthropic_key = _secret_value(domain_model.anthropic_key)
    db_model.google_ai_key = _secret_value(domain_model.google_ai_key)
    db_model.perplexity_key = _secret_value(domain_model.perplexity_key)
    db_model.replicate_key = _secret_value(domain_model.replicate_key)
    db_model.rapid_api_key = _secret_value(domain_model.rapid_api_key)
    db_model.coinmarketcap_key = _secret_value(domain_model.coinmarketcap_key)
    db_model.twelve_data_api_key = _secret_value(domain_model.twelve_data_api_key)
    db_model.x_key = _secret_value(domain_model.x_key)
    db_model.x_ai_key = _secret_value(domain_model.x_ai_key)

    db_model.tool_choice_chat = domain_model.tool_choice_chat
    db_model.tool_choice_reasoning = domain_model.tool_choice_reasoning
    db_model.tool_choice_copywriting = domain_model.tool_choice_copywriting
    db_model.tool_choice_vision = domain_model.tool_choice_vision
    db_model.tool_choice_hearing = domain_model.tool_choice_hearing
    db_model.tool_choice_images_gen = domain_model.tool_choice_images_gen
    db_model.tool_choice_videos_gen = domain_model.tool_choice_videos_gen
    db_model.tool_choice_images_edit = domain_model.tool_choice_images_edit
    db_model.tool_choice_search = domain_model.tool_choice_search
    db_model.tool_choice_embedding = domain_model.tool_choice_embedding
    db_model.tool_choice_api_fiat_exchange = domain_model.tool_choice_api_fiat_exchange
    db_model.tool_choice_api_crypto_exchange = domain_model.tool_choice_api_crypto_exchange
    db_model.tool_choice_api_stock_quote = domain_model.tool_choice_api_stock_quote
    db_model.tool_choice_api_twitter = domain_model.tool_choice_api_twitter

    db_model.credit_balance = domain_model.credit_balance

    db_model.is_on_waitlist = domain_model.is_on_waitlist
    db_model.is_invited_to_start = domain_model.is_invited_to_start
    db_model.are_policies_accepted = domain_model.are_policies_accepted

    db_model.connect_key = domain_model.connect_key
    db_model.group = domain_model.group


def from_remote_data(remote_data: UserRemoteData) -> User:
    return User(
        full_name = remote_data.full_name,

        telegram_username = remote_data.telegram_username,
        telegram_chat_id = remote_data.telegram_chat_id,
        telegram_user_id = remote_data.telegram_user_id,

        whatsapp_user_id = remote_data.whatsapp_user_id,
        whatsapp_phone_number = remote_data.whatsapp_phone_number,
    )


def apply_remote_data(
    user: User,
    remote_data: UserRemoteData,
) -> User:
    overrides = {}
    if remote_data.full_name is not None and not user.full_name:
        overrides["full_name"] = remote_data.full_name

    if remote_data.telegram_username is not None:
        overrides["telegram_username"] = remote_data.telegram_username
    if remote_data.telegram_chat_id is not None and user.telegram_chat_id is None:
        overrides["telegram_chat_id"] = remote_data.telegram_chat_id
    if remote_data.telegram_user_id is not None:
        overrides["telegram_user_id"] = remote_data.telegram_user_id

    if remote_data.whatsapp_user_id is not None:
        overrides["whatsapp_user_id"] = remote_data.whatsapp_user_id
    if remote_data.whatsapp_phone_number is not None:
        overrides["whatsapp_phone_number"] = remote_data.whatsapp_phone_number

    return replace(user, **overrides)
