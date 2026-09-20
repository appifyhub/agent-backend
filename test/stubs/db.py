from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from db.model.chat_attachment import ChatAttachmentDB
from db.model.chat_config import ChatConfigDB
from db.model.chat_membership import ChatMembershipDB
from db.model.chat_message import ChatMessageDB
from db.model.chat_message_burst import ChatMessageBurstDB
from db.model.purchase_record import PurchaseRecordDB
from db.model.usage_record import UsageRecordDB
from db.model.user import UserDB


def user_db(**overrides: Any) -> UserDB:
    defaults = {
        "id": UUID("11111111-1111-4111-8111-a11111111111"),
        "created_at": date(2026, 1, 15),
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
        "connect_key": "MARK-JHNS-2026",
        "group": UserDB.Group.standard,
    }
    return UserDB(**(defaults | overrides))


def chat_message_db(**overrides: Any) -> ChatMessageDB:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "author_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "message_id": "message-123",
        "sent_at": datetime(2026, 1, 15, 12, 0, 0),
        "text": "Hello from Mark Johnson.",
        "is_temporary": False,
        "ingestion_order": 1,
    }
    return ChatMessageDB(**(defaults | overrides))


def chat_config_db(**overrides: Any) -> ChatConfigDB:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "external_id": "telegram-chat-123",
        "language_iso_code": "en",
        "language_name": "English",
        "title": "Mark Johnson's Chat",
        "is_private": True,
        "reply_chance_percent": 100,
        "release_notifications": ChatConfigDB.ReleaseNotifications.major,
        "media_mode": ChatConfigDB.MediaMode.photo,
        "chat_type": ChatConfigDB.ChatType.telegram,
    }
    return ChatConfigDB(**(defaults | overrides))


def chat_attachment_db(**overrides: Any) -> ChatAttachmentDB:
    defaults = {
        "id": "attachment-123",
        "external_id": "telegram-file-123",
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "message_id": "message-123",
        "uploader_user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "created_at": datetime(2026, 1, 15, 12, 0, 0),
        "size": 245_760,
        "last_url": "https://example.com/attachments/photo.jpg",
        "extension": "jpg",
        "mime_type": "image/jpeg",
    }
    return ChatAttachmentDB(**(defaults | overrides))


def chat_membership_db(**overrides: Any) -> ChatMembershipDB:
    defaults = {
        "user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "is_admin": False,
        "use_about_me": True,
        "use_custom_prompt": True,
        "max_output_tokens": 3_500,
        "max_chat_history_depth": 30,
        "max_iterations": 20,
    }
    return ChatMembershipDB(**(defaults | overrides))


def chat_message_burst_db(**overrides: Any) -> ChatMessageBurstDB:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "author_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "message_count": 3,
        "process_after": datetime(2026, 1, 15, 12, 0, 2),
        "last_message_sent_at": datetime(2026, 1, 15, 12, 0, 0),
        "last_message_ingestion_order": 3,
        "is_addressed": True,
        "is_processing": False,
    }
    return ChatMessageBurstDB(**(defaults | overrides))


def purchase_record_db(**overrides: Any) -> PurchaseRecordDB:
    defaults = {
        "id": UUID("33333333-3333-4333-8333-c33333333333"),
        "user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "seller_id": "seller-123",
        "sale_id": "sale-456",
        "sale_timestamp": datetime(2026, 1, 15, 12, 0, tzinfo = timezone.utc),
        "price": 1_000,
        "product_id": "product-123",
        "product_name": "Test Product",
        "product_permalink": "https://example.com/products/test-product",
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
    return PurchaseRecordDB(**(defaults | overrides))


def usage_record_db(**overrides: Any) -> UsageRecordDB:
    defaults = {
        "id": UUID("44444444-4444-4444-8444-d44444444444"),
        "user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "payer_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "uses_credits": True,
        "is_failed": False,
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "tool_id": "gpt-5.5",
        "tool_name": "GPT 5.5",
        "provider_id": "open-ai",
        "provider_name": "OpenAI",
        "purpose": "chat",
        "timestamp": datetime(2026, 1, 15, 12, 0, tzinfo = timezone.utc),
        "runtime_seconds": 1.5,
        "remote_runtime_seconds": 0.5,
        "model_cost_credits": 0.1,
        "remote_runtime_cost_credits": 0.2,
        "api_call_cost_credits": 0.3,
        "maintenance_fee_credits": 0.4,
        "total_cost_credits": 1.0,
        "input_tokens": 100,
        "output_tokens": 200,
        "search_tokens": 50,
        "total_tokens": 350,
        "output_image_sizes": [],
        "input_image_sizes": [],
        "output_video_size": None,
        "output_video_duration_seconds": None,
        "counterpart_id": None,
        "note": None,
        "participant_details": None,
    }
    return UsageRecordDB(**(defaults | overrides))
