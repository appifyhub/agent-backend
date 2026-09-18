from typing import Any

from api.model.chat_config_payload import ChatConfigPayload
from api.model.chat_config_response import ChatConfigResponse
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.chat_settings_response import ChatSettingsResponse
from api.model.user_chat_config_payload import UserChatConfigPayload
from api.model.user_chat_config_response import UserChatConfigResponse
from api.model.user_settings_payload import UserSettingsPayload
from api.model.user_settings_response import UserSettingsResponse


def user_settings_payload(**overrides: Any) -> UserSettingsPayload:
    defaults = {
        "full_name": "Mark Johnson",
        "about_me": "Software engineer and Python enthusiast.",
        "custom_prompt": "Be concise, practical, and accurate.",
        "open_ai_key": "sk-test-open-ai",
        "anthropic_key": "sk-test-anthropic",
        "google_ai_key": "test-google-ai-key",
        "perplexity_key": "pplx-test-key",
        "replicate_key": "r8_test_replicate",
        "rapid_api_key": "test-rapid-api-key",
        "coinmarketcap_key": "test-coinmarketcap-key",
        "twelve_data_api_key": "test-twelve-data-key",
        "x_key": "test-x-key",
        "x_ai_key": "test-x-ai-key",
        "tool_choice_chat": "openai-gpt-5",
        "tool_choice_reasoning": "anthropic-claude-sonnet",
        "tool_choice_copywriting": "openai-gpt-5",
        "tool_choice_vision": "openai-gpt-5",
        "tool_choice_hearing": "openai-whisper",
        "tool_choice_images_gen": "openai-gpt-image",
        "tool_choice_videos_gen": "replicate-video",
        "tool_choice_search": "perplexity-search",
        "tool_choice_embedding": "openai-text-embedding",
        "tool_choice_api_fiat_exchange": "rapid-api-fiat-exchange",
        "tool_choice_api_crypto_exchange": "coinmarketcap-crypto-exchange",
        "tool_choice_api_stock_quote": "twelve-data-stock-quote",
        "tool_choice_api_twitter": "rapid-api-twitter",
        "are_policies_accepted": True,
    }
    return UserSettingsPayload(**(defaults | overrides))


def user_settings_response(**overrides: Any) -> UserSettingsResponse:
    defaults = {
        "id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-01-15",
        "full_name": "Mark Johnson",
        "about_me": "Software engineer and Python enthusiast.",
        "custom_prompt": "Be concise, practical, and accurate.",
        "telegram_username": "mark_johnson",
        "telegram_chat_id": "123456789",
        "telegram_user_id": 123456789,
        "whatsapp_user_id": "whatsapp-mark-johnson",
        "whatsapp_phone_number": "+15551234567",
        "open_ai_key": "sk-test-open-ai",
        "anthropic_key": "sk-test-anthropic",
        "google_ai_key": "test-google-ai-key",
        "perplexity_key": "pplx-test-key",
        "replicate_key": "r8_test_replicate",
        "rapid_api_key": "test-rapid-api-key",
        "coinmarketcap_key": "test-coinmarketcap-key",
        "twelve_data_api_key": "test-twelve-data-key",
        "x_key": "test-x-key",
        "x_ai_key": "test-x-ai-key",
        "tool_choice_chat": "openai-gpt-5",
        "tool_choice_reasoning": "anthropic-claude-sonnet",
        "tool_choice_copywriting": "openai-gpt-5",
        "tool_choice_vision": "openai-gpt-5",
        "tool_choice_hearing": "openai-whisper",
        "tool_choice_images_gen": "openai-gpt-image",
        "tool_choice_videos_gen": "replicate-video",
        "tool_choice_search": "perplexity-search",
        "tool_choice_embedding": "openai-text-embedding",
        "tool_choice_api_fiat_exchange": "rapid-api-fiat-exchange",
        "tool_choice_api_crypto_exchange": "coinmarketcap-crypto-exchange",
        "tool_choice_api_stock_quote": "twelve-data-stock-quote",
        "tool_choice_api_twitter": "rapid-api-twitter",
        "credit_balance": 100.0,
        "is_on_waitlist": False,
        "is_invited_to_start": True,
        "are_policies_accepted": True,
        "is_sponsored": False,
        "group": "standard",
    }
    return UserSettingsResponse(**(defaults | overrides))


def chat_config_payload(**overrides: Any) -> ChatConfigPayload:
    defaults = {
        "language_name": "English",
        "language_iso_code": "en",
        "reply_chance_percent": 100,
        "release_notifications": "major",
        "media_mode": "photo",
    }
    return ChatConfigPayload(**(defaults | overrides))


def chat_config_response(**overrides: Any) -> ChatConfigResponse:
    defaults = {
        "chat_id": "22222222-2222-4222-8222-222222222222",
        "title": "Mark Johnson's Chat",
        "platform": "telegram",
        "language_name": "English",
        "language_iso_code": "en",
        "reply_chance_percent": 100,
        "release_notifications": "major",
        "media_mode": "photo",
        "is_private": True,
        "is_own": True,
        "is_admin": True,
    }
    return ChatConfigResponse(**(defaults | overrides))


def user_chat_config_payload(**overrides: Any) -> UserChatConfigPayload:
    defaults = {
        "use_about_me": True,
        "use_custom_prompt": True,
        "max_output_tokens": 2_048,
        "max_chat_history_depth": 20,
        "max_iterations": 10,
    }
    return UserChatConfigPayload(**(defaults | overrides))


def user_chat_config_response(**overrides: Any) -> UserChatConfigResponse:
    defaults = {
        "use_about_me": True,
        "use_custom_prompt": True,
        "max_output_tokens": 2_048,
        "max_chat_history_depth": 20,
        "max_iterations": 10,
    }
    return UserChatConfigResponse(**(defaults | overrides))


def chat_settings_payload(**overrides: Any) -> ChatSettingsPayload:
    defaults: dict[str, Any] = {}
    if "chat_config" not in overrides:
        defaults["chat_config"] = chat_config_payload()
    if "user_chat_config" not in overrides:
        defaults["user_chat_config"] = user_chat_config_payload()
    return ChatSettingsPayload(**(defaults | overrides))


def chat_settings_response(**overrides: Any) -> ChatSettingsResponse:
    defaults: dict[str, Any] = {}
    if "chat_config" not in overrides:
        defaults["chat_config"] = chat_config_response()
    if "user_chat_config" not in overrides:
        defaults["user_chat_config"] = user_chat_config_response()
    return ChatSettingsResponse(**(defaults | overrides))
