from typing import Any

from api.auth import PublicAttachmentTokenClaims
from api.model.chat_config_payload import ChatConfigPayload
from api.model.chat_config_response import ChatConfigResponse
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.chat_settings_response import ChatSettingsResponse
from api.model.credit_transfer_payload import CreditTransferPayload
from api.model.gumroad_ping_payload import GumroadPingPayload
from api.model.release_output_payload import ReleaseOutputPayload
from api.model.settings_link_response import SettingsLinkResponse
from api.model.sponsorship_payload import SponsorshipPayload
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
        "tool_choice_chat": "gpt-5.5",
        "tool_choice_reasoning": "claude-sonnet-4-6",
        "tool_choice_copywriting": "gpt-5.5",
        "tool_choice_vision": "claude-sonnet-4-6",
        "tool_choice_hearing": "whisper-1",
        "tool_choice_images_gen": "black-forest-labs/flux-2-pro",
        "tool_choice_videos_gen": "prunaai/p-video",
        "tool_choice_search": "sonar",
        "tool_choice_embedding": "text-embedding-3-large",
        "tool_choice_api_fiat_exchange": "currency-converter5.p.rapidapi.com",
        "tool_choice_api_crypto_exchange": "v1.cryptocurrency.quotes.latest",
        "tool_choice_api_stock_quote": "quote",
        "tool_choice_api_twitter": "x.api-v2-post.read",
        "are_policies_accepted": True,
    }
    return UserSettingsPayload(**(defaults | overrides))


def user_settings_response(**overrides: Any) -> UserSettingsResponse:
    defaults = {
        "id": "11111111-1111-4111-8111-a11111111111",
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
        "chat_id": "22222222-2222-4222-8222-b22222222222",
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


def release_output_payload(**overrides: Any) -> ReleaseOutputPayload:
    defaults = {
        "release_output_b64": "eyJyZWxlYXNlIjoidGVzdCJ9",
    }
    return ReleaseOutputPayload(**(defaults | overrides))


def settings_link_response(**overrides: Any) -> SettingsLinkResponse:
    defaults = {
        "settings_link": "https://example.com/settings",
    }
    return SettingsLinkResponse(**(defaults | overrides))


def public_attachment_token_claims(**overrides: Any) -> PublicAttachmentTokenClaims:
    defaults = {
        "attachment_id": "attachment-123",
        "chat_id": "22222222222242228222b22222222222",
        "issuer_user_id": "11111111111141118111a11111111111",
    }
    return PublicAttachmentTokenClaims(**(defaults | overrides))


def sponsorship_payload(**overrides: Any) -> SponsorshipPayload:
    defaults = {
        "platform": "telegram",
        "platform_handle": "receiver_handle",
    }
    return SponsorshipPayload(**(defaults | overrides))


def credit_transfer_payload(**overrides: Any) -> CreditTransferPayload:
    defaults = {
        "platform": "telegram",
        "platform_handle": "receiver_handle",
        "amount": 25.0,
        "note": "Thanks for helping.",
    }
    return CreditTransferPayload(**(defaults | overrides))


def gumroad_ping_payload(**overrides: Any) -> GumroadPingPayload:
    defaults = {
        "seller_id": "seller-123",
        "sale_id": "sale-456",
        "sale_timestamp": "2024-01-01T00:00:00Z",
        "price": 1_000,
        "product_id": "product-789",
        "product_name": "Test Product",
        "product_permalink": "https://example.com/product",
        "short_product_id": "short-123",
        "license_key": "LICENSE-KEY-ABC",
        "quantity": 1,
        "gumroad_fee": 100,
        "affiliate_credit_amount_cents": 50,
        "discover_fee_charge": False,
        "url_params": {},
        "custom_fields": {},
        "test": False,
        "is_preorder_authorization": False,
        "refunded": False,
    }
    return GumroadPingPayload(**(defaults | overrides))
