from pydantic import SecretStr

from api.model.user_settings_payload import UserSettingsPayload
from api.model.user_settings_response import UserSettingsResponse
from db.schema.user import User, UserSave
from util.functions import mask_secret


def api_to_domain(payload: UserSettingsPayload, existing_user: User) -> UserSave:
    # We will set the updated token fields: None -> preserve, empty string -> clear, value -> set
    # All fields are already stripped in the payload model validators
    user_save = UserSave(**existing_user.model_dump())

    # @formatter:off
    if payload.full_name is not None:
        user_save.full_name = payload.full_name if payload.full_name else None
    if payload.about_me is not None:
        user_save.about_me = SecretStr(payload.about_me) if payload.about_me else None
    if payload.custom_prompt is not None:
        user_save.custom_prompt = SecretStr(payload.custom_prompt) if payload.custom_prompt else None

    if payload.open_ai_key is not None:
        user_save.open_ai_key = SecretStr(payload.open_ai_key) if payload.open_ai_key else None
    if payload.anthropic_key is not None:
        user_save.anthropic_key = SecretStr(payload.anthropic_key) if payload.anthropic_key else None
    if payload.google_ai_key is not None:
        user_save.google_ai_key = SecretStr(payload.google_ai_key) if payload.google_ai_key else None
    if payload.perplexity_key is not None:
        user_save.perplexity_key = SecretStr(payload.perplexity_key) if payload.perplexity_key else None
    if payload.replicate_key is not None:
        user_save.replicate_key = SecretStr(payload.replicate_key) if payload.replicate_key else None
    if payload.rapid_api_key is not None:
        user_save.rapid_api_key = SecretStr(payload.rapid_api_key) if payload.rapid_api_key else None
    if payload.coinmarketcap_key is not None:
        user_save.coinmarketcap_key = SecretStr(payload.coinmarketcap_key) if payload.coinmarketcap_key else None
    if payload.x_key is not None:
        user_save.x_key = SecretStr(payload.x_key) if payload.x_key else None
    if payload.x_ai_key is not None:
        user_save.x_ai_key = SecretStr(payload.x_ai_key) if payload.x_ai_key else None

    if payload.tool_choice_chat is not None:
        user_save.tool_choice_chat = payload.tool_choice_chat if payload.tool_choice_chat else None
    if payload.tool_choice_reasoning is not None:
        user_save.tool_choice_reasoning = payload.tool_choice_reasoning if payload.tool_choice_reasoning else None
    if payload.tool_choice_copywriting is not None:
        user_save.tool_choice_copywriting = payload.tool_choice_copywriting if payload.tool_choice_copywriting else None
    if payload.tool_choice_vision is not None:
        user_save.tool_choice_vision = payload.tool_choice_vision if payload.tool_choice_vision else None
    if payload.tool_choice_hearing is not None:
        user_save.tool_choice_hearing = payload.tool_choice_hearing if payload.tool_choice_hearing else None
    if payload.tool_choice_images_gen is not None:
        user_save.tool_choice_images_gen = payload.tool_choice_images_gen if payload.tool_choice_images_gen else None
    if payload.tool_choice_images_edit is not None:
        user_save.tool_choice_images_edit = payload.tool_choice_images_edit if payload.tool_choice_images_edit else None
    if payload.tool_choice_search is not None:
        user_save.tool_choice_search = payload.tool_choice_search if payload.tool_choice_search else None
    if payload.tool_choice_embedding is not None:
        user_save.tool_choice_embedding = payload.tool_choice_embedding if payload.tool_choice_embedding else None
    if payload.tool_choice_api_fiat_exchange is not None:
        user_save.tool_choice_api_fiat_exchange = payload.tool_choice_api_fiat_exchange if payload.tool_choice_api_fiat_exchange else None  # noqa: E501
    if payload.tool_choice_api_crypto_exchange is not None:
        user_save.tool_choice_api_crypto_exchange = payload.tool_choice_api_crypto_exchange if payload.tool_choice_api_crypto_exchange else None  # noqa: E501
    if payload.tool_choice_api_twitter is not None:
        user_save.tool_choice_api_twitter = payload.tool_choice_api_twitter if payload.tool_choice_api_twitter else None

    if payload.are_policies_accepted is not None:
        user_save.are_policies_accepted = payload.are_policies_accepted
    # @formatter:on

    return user_save


def domain_to_api(user: User, is_sponsored: bool) -> UserSettingsResponse:
    return UserSettingsResponse(
        id = user.id.hex,
        full_name = user.full_name,
        about_me = user.about_me.get_secret_value() if user.about_me else None,
        custom_prompt = user.custom_prompt.get_secret_value() if user.custom_prompt else None,
        group = user.group.value,

        telegram_username = user.telegram_username,
        telegram_chat_id = user.telegram_chat_id,
        telegram_user_id = user.telegram_user_id,

        whatsapp_user_id = user.whatsapp_user_id,
        whatsapp_phone_number = (
            user.whatsapp_phone_number.get_secret_value()
            if user.whatsapp_phone_number else None
        ),

        open_ai_key = mask_secret(user.open_ai_key.get_secret_value() if user.open_ai_key else None),
        anthropic_key = mask_secret(user.anthropic_key.get_secret_value() if user.anthropic_key else None),
        google_ai_key = mask_secret(user.google_ai_key.get_secret_value() if user.google_ai_key else None),
        perplexity_key = mask_secret(user.perplexity_key.get_secret_value() if user.perplexity_key else None),
        replicate_key = mask_secret(user.replicate_key.get_secret_value() if user.replicate_key else None),
        rapid_api_key = mask_secret(user.rapid_api_key.get_secret_value() if user.rapid_api_key else None),
        coinmarketcap_key = mask_secret(user.coinmarketcap_key.get_secret_value() if user.coinmarketcap_key else None),
        x_key = mask_secret(user.x_key.get_secret_value() if user.x_key else None),
        x_ai_key = mask_secret(user.x_ai_key.get_secret_value() if user.x_ai_key else None),

        tool_choice_chat = user.tool_choice_chat,
        tool_choice_reasoning = user.tool_choice_reasoning,
        tool_choice_copywriting = user.tool_choice_copywriting,
        tool_choice_vision = user.tool_choice_vision,
        tool_choice_hearing = user.tool_choice_hearing,
        tool_choice_images_gen = user.tool_choice_images_gen,
        tool_choice_images_edit = user.tool_choice_images_edit,
        tool_choice_search = user.tool_choice_search,
        tool_choice_embedding = user.tool_choice_embedding,
        tool_choice_api_fiat_exchange = user.tool_choice_api_fiat_exchange,
        tool_choice_api_crypto_exchange = user.tool_choice_api_crypto_exchange,
        tool_choice_api_twitter = user.tool_choice_api_twitter,

        credit_balance = user.credit_balance,

        is_on_waitlist = user.is_on_waitlist,
        is_invited_to_start = user.is_invited_to_start,
        are_policies_accepted = user.are_policies_accepted,
        is_sponsored = is_sponsored,

        created_at = user.created_at.isoformat(),
    )
