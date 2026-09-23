from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from features.accounting.purchases.purchase_aggregates import ProductAggregateStats, ProductInfo, PurchaseAggregates
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.usage.image_usage_stats import ImageUsageStats
from features.accounting.usage.llm_usage_stats import LLMUsageStats
from features.accounting.usage.participant_details import ParticipantDetails, ParticipantInfo
from features.accounting.usage.usage_aggregates import AggregateStats, ProviderInfo, ToolInfo, UsageAggregates
from features.accounting.usage.usage_record import UsageRecord
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.attachment.chat_attachment_service import RemoteAttachmentContent, ResolvedAttachmentStream
from features.chat.attachment.storage.attachment_storage import PublicAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.membership.chat_membership import ChatMembership
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.message.formatted_chat_message import (
    FormattedAttachmentPart,
    FormattedAttachmentReference,
    FormattedChatMessage,
    FormattedQuotePart,
    FormattedTextPart,
)
from features.chat.message_burst import ClaimedChatMessageBurst, ScheduledChatMessageBurst
from features.currencies.asset_alert_service import AssetAlertService
from features.currencies.asset_price import AssetPrice, AssetType, StockQuote
from features.currencies.price_alert import PriceAlert
from features.external_tools.access_token_resolver import ResolvedToken
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_6_SONNET,
    CRYPTO_CURRENCY_EXCHANGE,
    FIAT_CURRENCY_EXCHANGE,
    GPT_5_5,
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    SONAR,
    TEXT_EMBEDDING_5_LARGE,
    TWELVE_DATA_STOCK_QUOTE,
    VIDEO_GEN_P_VIDEO,
    WHISPER_1,
    X_READ_POST,
)
from features.prompting.prompt_composer import PromptFragment, PromptSection
from features.social_cards.social_card_models import (
    SocialAuthor,
    SocialCardMode,
    SocialCardRenderResult,
    SocialCardTemplateResult,
    SocialCardVideoInput,
    SocialDynamicMedia,
    SocialLinkPreview,
    SocialLinkPreviewAsset,
    SocialMediaAsset,
    SocialMediaItem,
    SocialMediaKind,
    SocialMediaPlacement,
    SocialPlatformBrand,
    SocialPost,
    SocialPostRenderAssets,
)
from features.sponsorships.sponsorship import Sponsorship
from features.tools_cache.tools_cache import ToolsCache
from features.users.user import User
from features.users.user_remote_data import UserRemoteData
from features.videos.video_file_utils import VideoMetadata
from util.config import ConfiguredProduct


def user(**overrides: Any) -> User:
    defaults = {
        "id": UUID("11111111-1111-4111-8111-a11111111111"),
        "created_at": date(2026, 1, 15),
        "full_name": "Mark Johnson",
        "about_me": SecretStr("Software engineer and Python enthusiast."),
        "custom_prompt": SecretStr("Be concise, practical, and accurate."),
        "telegram_username": "mark_johnson",
        "telegram_chat_id": "123456789",
        "telegram_user_id": 123456789,
        "whatsapp_user_id": "whatsapp-mark-johnson",
        "whatsapp_phone_number": SecretStr("+15551234567"),
        "open_ai_key": SecretStr("sk-test-open-ai"),
        "anthropic_key": SecretStr("sk-test-anthropic"),
        "google_ai_key": SecretStr("test-google-ai-key"),
        "perplexity_key": SecretStr("pplx-test-key"),
        "replicate_key": SecretStr("r8_test_replicate"),
        "rapid_api_key": SecretStr("test-rapid-api-key"),
        "coinmarketcap_key": SecretStr("test-coinmarketcap-key"),
        "twelve_data_api_key": SecretStr("test-twelve-data-key"),
        "x_key": SecretStr("test-x-key"),
        "x_ai_key": SecretStr("test-x-ai-key"),
        "tool_choice_chat": GPT_5_5.id,
        "tool_choice_reasoning": CLAUDE_4_6_SONNET.id,
        "tool_choice_copywriting": GPT_5_5.id,
        "tool_choice_vision": CLAUDE_4_6_SONNET.id,
        "tool_choice_hearing": WHISPER_1.id,
        "tool_choice_images_gen": IMAGE_GEN_EDIT_FLUX_2_PRO.id,
        "tool_choice_videos_gen": VIDEO_GEN_P_VIDEO.id,
        "tool_choice_search": SONAR.id,
        "tool_choice_embedding": TEXT_EMBEDDING_5_LARGE.id,
        "tool_choice_api_fiat_exchange": FIAT_CURRENCY_EXCHANGE.id,
        "tool_choice_api_crypto_exchange": CRYPTO_CURRENCY_EXCHANGE.id,
        "tool_choice_api_stock_quote": TWELVE_DATA_STOCK_QUOTE.id,
        "tool_choice_api_twitter": X_READ_POST.id,
        "credit_balance": 100.0,
        "is_on_waitlist": False,
        "is_invited_to_start": True,
        "are_policies_accepted": True,
        "connect_key": "MARK-JHNS-2026",
        "group": UserDB.Group.standard,
    }
    return User(**(defaults | overrides))


def user_remote_data(**overrides: Any) -> UserRemoteData:
    defaults = {
        "full_name": "Mark Johnson",
        "telegram_username": "mark_johnson",
        "telegram_chat_id": "123456789",
        "telegram_user_id": 123456789,
        "whatsapp_user_id": "whatsapp-mark-johnson",
        "whatsapp_phone_number": SecretStr("+15551234567"),
    }
    return UserRemoteData(**(defaults | overrides))


def chat_message(**overrides: Any) -> ChatMessage:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "message_id": "message-123",
        "text": "Hello from Mark Johnson.",
        "author_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "sent_at": datetime(2026, 1, 15, 12, 0, 0),
        "is_temporary": False,
        "ingestion_order": 1,
    }
    return ChatMessage(**(defaults | overrides))


def chat_message_remote_data(**overrides: Any) -> ChatMessageRemoteData:
    defaults = {
        "message_id": "message-123",
        "sent_at": datetime(2026, 1, 15, 12, 0, 0),
        "text": "Hello from Mark Johnson.",
        "replied_to_message_id": None,
        "quote_text": None,
    }
    return ChatMessageRemoteData(**(defaults | overrides))


def chat_config(**overrides: Any) -> ChatConfig:
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
    return ChatConfig(**(defaults | overrides))


def chat_config_remote_data(**overrides: Any) -> ChatConfigRemoteData:
    defaults = {
        "external_id": "telegram-chat-123",
        "chat_type": ChatConfigDB.ChatType.telegram,
        "title": None,
        "is_private": None,
        "language_iso_code": None,
    }
    return ChatConfigRemoteData(**(defaults | overrides))


def chat_attachment(**overrides: Any) -> ChatAttachment:
    defaults = {
        "id": "attachment-123",
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "uploader_user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "message_id": "message-123",
        "external_id": "telegram-file-123",
        "created_at": datetime(2026, 1, 15, 12, 0, 0),
        "size": 245_760,
        "last_url": "https://example.com/attachments/photo.jpg",
        "extension": "jpg",
        "mime_type": "image/jpeg",
    }
    return ChatAttachment(**(defaults | overrides))


def chat_attachment_remote_data(**overrides: Any) -> ChatAttachmentRemoteData:
    defaults = {
        "external_id": "telegram-file-123",
        "message_id": "message-123",
        "size": 245_760,
        "last_url": "https://example.com/attachments/photo.jpg",
        "extension": "jpg",
        "mime_type": "image/jpeg",
    }
    return ChatAttachmentRemoteData(**(defaults | overrides))


def remote_attachment_content(**overrides: Any) -> RemoteAttachmentContent:
    defaults = {
        "content": b"attachment content",
        "response_mime_type": "application/octet-stream",
    }
    return RemoteAttachmentContent(**(defaults | overrides))


def public_attachment(**overrides: Any) -> PublicAttachment:
    defaults = {
        "id": "attachment-123",
        "url": "https://example.com/attachments/photo.jpg",
        "valid_until": 1_800_000_000,
    }
    return PublicAttachment(**(defaults | overrides))


def tools_cache(**overrides: Any) -> ToolsCache:
    defaults = {
        "key": "test-cache-key",
        "value": "cached tool result",
        "created_at": datetime(2026, 1, 15, 12, 0, 0),
        "expires_at": None,
    }
    return ToolsCache(**(defaults | overrides))


def ingested_chat_message(**overrides: Any) -> IngestedChatMessage:
    chat = overrides.pop("chat") if "chat" in overrides else chat_config()
    author = overrides.pop("author") if "author" in overrides else user()
    message = (
        overrides.pop("message")
        if "message" in overrides
        else chat_message(
            chat_id = chat.chat_id,
            author_id = author.id if author else None,
        )
    )
    defaults = {
        "chat": chat,
        "author": author,
        "message": message,
        "attachments": [],
        "raw_message_text": "Hello from Mark Johnson.",
    }
    return IngestedChatMessage(**(defaults | overrides))


def scheduled_chat_message_burst(**overrides: Any) -> ScheduledChatMessageBurst:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "author_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "message_count": 3,
        "wait_seconds": 1.5,
    }
    return ScheduledChatMessageBurst(**(defaults | overrides))


def claimed_chat_message_burst(**overrides: Any) -> ClaimedChatMessageBurst:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "author_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "message_count": 3,
        "last_message_sent_at": datetime(2026, 1, 15, 12, 0, 0),
        "last_message_ingestion_order": 3,
        "is_addressed": True,
    }
    return ClaimedChatMessageBurst(**(defaults | overrides))


def chat_membership(**overrides: Any) -> ChatMembership:
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
    return ChatMembership(**(defaults | overrides))


def cost_estimate(**overrides: Any) -> CostEstimate:
    defaults = {
        "input_1m_tokens": 1.0,
        "output_1m_tokens": 2.0,
        "search_1m_tokens": 0.5,
        "input_image_1k": 0.1,
        "input_image_2k": 0.2,
        "input_image_4k": 0.4,
        "input_image_8k": 0.8,
        "input_image_12k": 1.2,
        "output_image_1k": 0.5,
        "output_image_2k": 1.0,
        "output_image_4k": 2.0,
        "output_video_1k_second": 0.1,
        "output_video_2k_second": 0.2,
        "output_video_4k_second": 0.4,
        "api_call": 0.01,
        "second_of_runtime": 0.02,
        "web_search_query": 0.03,
    }
    return CostEstimate(**(defaults | overrides))


def external_tool_provider(**overrides: Any) -> ExternalToolProvider:
    defaults = {
        "id": "test-provider",
        "name": "Test Provider",
        "token_management_url": "https://example.com/settings/api-keys",
        "token_format": "test-...",
        "tools": ["test-chat-model"],
    }
    return ExternalToolProvider(**(defaults | overrides))


def external_tool(**overrides: Any) -> ExternalTool:
    defaults: dict[str, Any] = {
        "id": "test-chat-model",
        "name": "Test Chat Model",
        "types": [ToolType.chat],
        "max_input_images": 5,
    }
    if "provider" not in overrides:
        defaults["provider"] = external_tool_provider()
    if "cost_estimate" not in overrides:
        defaults["cost_estimate"] = cost_estimate()
    return ExternalTool(**(defaults | overrides))


def configured_tool(**overrides: Any) -> ConfiguredTool:
    defaults: dict[str, Any] = {
        "token": SecretStr("test-provider-token"),
        "purpose": ToolType.chat,
        "payer_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "uses_credits": False,
    }
    if "definition" not in overrides:
        defaults["definition"] = external_tool()
    return ConfiguredTool(**(defaults | overrides))


def formatted_text_part(**overrides: Any) -> FormattedTextPart:
    defaults = {
        "text": "Hello from Mark Johnson.",
    }
    return FormattedTextPart(**(defaults | overrides))


def formatted_attachment_reference(**overrides: Any) -> FormattedAttachmentReference:
    defaults = {
        "id": "attachment-123",
        "mime_type": "image/jpeg",
    }
    return FormattedAttachmentReference(**(defaults | overrides))


def formatted_attachment_part(**overrides: Any) -> FormattedAttachmentPart:
    defaults: dict[str, Any] = {}
    if "attachments" not in overrides:
        defaults["attachments"] = [formatted_attachment_reference()]
    return FormattedAttachmentPart(**(defaults | overrides))


def formatted_chat_message(**overrides: Any) -> FormattedChatMessage:
    defaults: dict[str, Any] = {}
    if "parts" not in overrides:
        defaults["parts"] = [formatted_text_part()]
    return FormattedChatMessage(**(defaults | overrides))


def formatted_quote_part(**overrides: Any) -> FormattedQuotePart:
    defaults: dict[str, Any] = {
        "depth": 1,
    }
    if "message" not in overrides:
        defaults["message"] = formatted_chat_message()
    return FormattedQuotePart(**(defaults | overrides))


def video_metadata(**overrides: Any) -> VideoMetadata:
    defaults = {
        "container": "mp4",
        "video_codecs": ("h264",),
        "audio_codecs": ("aac",),
        "pixel_formats": ("yuv420p",),
        "video_stream_count": 1,
        "audio_stream_count": 1,
        "width": 1920,
        "height": 1080,
        "duration_seconds": 12.0,
        "size_bytes": 1_048_576,
        "has_fast_start": True,
    }
    return VideoMetadata(**(defaults | overrides))


def resolved_attachment_stream(**overrides: Any) -> ResolvedAttachmentStream:
    defaults = {
        "stream": BytesIO(b"attachment-content"),
        "media_type": "application/octet-stream",
    }
    return ResolvedAttachmentStream(**(defaults | overrides))


def purchase_record(**overrides: Any) -> PurchaseRecord:
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
    return PurchaseRecord(**(defaults | overrides))


def product_aggregate_stats(**overrides: Any) -> ProductAggregateStats:
    defaults = {
        "record_count": 10,
        "total_cost_cents": 10_000,
        "total_net_cost_cents": 9_000,
    }
    return ProductAggregateStats(**(defaults | overrides))


def product_info(**overrides: Any) -> ProductInfo:
    defaults = {
        "id": "product-123",
        "name": "Test Product",
    }
    return ProductInfo(**(defaults | overrides))


def purchase_aggregates(**overrides: Any) -> PurchaseAggregates:
    defaults: dict[str, Any] = {
        "total_purchase_count": 10,
        "total_cost_cents": 10_000,
        "total_net_cost_cents": 9_000,
    }
    if "by_product" not in overrides:
        defaults["by_product"] = {"product-123": product_aggregate_stats()}
    if "all_products_used" not in overrides:
        defaults["all_products_used"] = [product_info()]
    return PurchaseAggregates(**(defaults | overrides))


def participant_info(**overrides: Any) -> ParticipantInfo:
    defaults = {
        "user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "full_name": "Mark Johnson",
        "platform": "telegram",
        "handle": "mark_johnson",
    }
    return ParticipantInfo(**(defaults | overrides))


def participant_details(**overrides: Any) -> ParticipantDetails:
    defaults: dict[str, Any] = {}
    if "payer" not in overrides:
        defaults["payer"] = participant_info()
    if "owner" not in overrides:
        defaults["owner"] = participant_info()
    if "counterpart" not in overrides:
        defaults["counterpart"] = participant_info(
            user_id = UUID("22222222-2222-4222-8222-b22222222222"),
            full_name = "Taylor Smith",
            handle = "taylor_smith",
        )
    return ParticipantDetails(**(defaults | overrides))


def usage_record(**overrides: Any) -> UsageRecord:
    defaults: dict[str, Any] = {
        "user_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "payer_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "uses_credits": True,
        "is_failed": False,
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "tool_purpose": ToolType.chat,
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
    }
    if "tool" not in overrides:
        defaults["tool"] = external_tool(
            id = GPT_5_5.id,
            name = GPT_5_5.name,
            provider = external_tool_provider(
                id = GPT_5_5.provider.id,
                name = GPT_5_5.provider.name,
                token_management_url = GPT_5_5.provider.token_management_url,
                token_format = GPT_5_5.provider.token_format,
                tools = list(GPT_5_5.provider.tools),
            ),
            types = list(GPT_5_5.types),
            cost_estimate = cost_estimate(
                input_1m_tokens = GPT_5_5.cost_estimate.input_1m_tokens,
                output_1m_tokens = GPT_5_5.cost_estimate.output_1m_tokens,
                search_1m_tokens = None,
                input_image_1k = None,
                input_image_2k = None,
                input_image_4k = None,
                input_image_8k = None,
                input_image_12k = None,
                output_image_1k = None,
                output_image_2k = None,
                output_image_4k = None,
                output_video_1k_second = None,
                output_video_2k_second = None,
                output_video_4k_second = None,
                api_call = None,
                second_of_runtime = None,
                web_search_query = None,
            ),
        )
    return UsageRecord(**(defaults | overrides))


def image_usage_stats(**overrides: Any) -> ImageUsageStats:
    defaults = {
        "input_tokens": 100,
        "output_tokens": 200,
        "total_tokens": 300,
        "remote_runtime_seconds": 1.5,
    }
    return ImageUsageStats(**(defaults | overrides))


def llm_usage_stats(**overrides: Any) -> LLMUsageStats:
    defaults = {
        "input_tokens": 100,
        "output_tokens": 200,
        "search_tokens": 50,
        "total_tokens": 350,
        "remote_runtime_seconds": 1.5,
    }
    return LLMUsageStats(**(defaults | overrides))


def aggregate_stats(**overrides: Any) -> AggregateStats:
    defaults = {
        "record_count": 10,
        "total_cost": 100.0,
    }
    return AggregateStats(**(defaults | overrides))


def tool_info(**overrides: Any) -> ToolInfo:
    defaults = {
        "id": "gpt-4o",
        "name": "GPT 4o",
    }
    return ToolInfo(**(defaults | overrides))


def provider_info(**overrides: Any) -> ProviderInfo:
    defaults = {
        "id": "open-ai",
        "name": "OpenAI",
    }
    return ProviderInfo(**(defaults | overrides))


def usage_aggregates(**overrides: Any) -> UsageAggregates:
    defaults: dict[str, Any] = {
        "total_records": 10,
        "total_cost_credits": 100.0,
        "total_runtime_seconds": 15.0,
        "all_purposes_used": ["chat"],
    }
    if "by_tool" not in overrides:
        defaults["by_tool"] = {"gpt-4o": aggregate_stats()}
    if "by_purpose" not in overrides:
        defaults["by_purpose"] = {"chat": aggregate_stats()}
    if "by_provider" not in overrides:
        defaults["by_provider"] = {"open-ai": aggregate_stats()}
    if "all_tools_used" not in overrides:
        defaults["all_tools_used"] = [tool_info()]
    if "all_providers_used" not in overrides:
        defaults["all_providers_used"] = [provider_info()]
    return UsageAggregates(**(defaults | overrides))


def sponsorship(**overrides: Any) -> Sponsorship:
    defaults = {
        "sponsor_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "receiver_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "sponsored_at": datetime(2026, 1, 15, 12, 0),
        "accepted_at": datetime(2026, 1, 16, 12, 0),
    }
    return Sponsorship(**(defaults | overrides))


def configured_product(**overrides: Any) -> ConfiguredProduct:
    defaults = {
        "id": "product-123",
        "credits": 100,
        "name": "Starter Pack",
        "url": "https://example.com/product-123",
    }
    return ConfiguredProduct(**(defaults | overrides))


def prompt_fragment(**overrides: Any) -> PromptFragment:
    defaults = {
        "id": "agent-context",
        "content": "You are a helpful assistant.",
        "section": PromptSection.context,
    }
    return PromptFragment(**(defaults | overrides))


def price_alert(**overrides: Any) -> PriceAlert:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "owner_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "asset_type": AssetType.crypto,
        "asset_id": "BTC",
        "currency": "USD",
        "threshold_percent": 5,
        "last_price": 50_000.0,
        "last_price_time": datetime(2026, 1, 15, 12, 0),
    }
    return PriceAlert(**(defaults | overrides))


def triggered_alert(**overrides: Any) -> AssetAlertService.TriggeredAlert:
    defaults = {
        "chat_id": UUID("22222222-2222-4222-8222-b22222222222"),
        "owner_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "asset_type": AssetType.crypto,
        "asset_id": "BTC",
        "currency": "USD",
        "threshold_percent": 5,
        "old_price": 50_000.0,
        "old_price_time": "2026-01-15 12:00 UTC",
        "new_price": 55_000.0,
        "new_price_time": "2026-01-16 12:00 UTC",
        "price_change_percent": 10,
    }
    return AssetAlertService.TriggeredAlert(**(defaults | overrides))


def resolved_token(**overrides: Any) -> ResolvedToken:
    defaults = {
        "token": SecretStr("test-provider-token"),
        "payer_id": UUID("11111111-1111-4111-8111-a11111111111"),
        "uses_credits": False,
    }
    return ResolvedToken(**(defaults | overrides))


def social_platform_brand(**overrides: Any) -> SocialPlatformBrand:
    defaults = {
        "platform_id": "x",
        "display_name": "X",
        "logo_light_key": "x-light",
        "logo_dark_key": "x-dark",
    }
    return SocialPlatformBrand(**(defaults | overrides))


def social_author(**overrides: Any) -> SocialAuthor:
    defaults = {
        "handle": "@mark_johnson",
        "additional_profile_info": "Software engineer",
        "avatar_url": "https://example.com/avatar.jpg",
        "profile_url": "https://x.com/mark_johnson",
        "bio": "Building useful software.",
    }
    return SocialAuthor(**(defaults | overrides))


def social_dynamic_media(**overrides: Any) -> SocialDynamicMedia:
    defaults = {
        "playback_url": "https://example.com/media/video.mp4",
        "audio_url": "https://example.com/media/audio.mp3",
        "duration_seconds": 12.0,
        "width": 1280,
        "height": 720,
    }
    return SocialDynamicMedia(**(defaults | overrides))


def social_media_item(**overrides: Any) -> SocialMediaItem:
    defaults = {
        "kind": SocialMediaKind.IMAGE,
        "url": "https://example.com/media/photo.jpg",
        "preview_url": "https://example.com/media/photo-preview.jpg",
        "alt_text": "A city skyline at sunset.",
        "dynamic_media": None,
    }
    return SocialMediaItem(**(defaults | overrides))


def social_link_preview(**overrides: Any) -> SocialLinkPreview:
    defaults = {
        "expanded_url": "https://example.com/articles/story",
        "domain": "example.com",
        "title": "Example story",
        "description": "A concise preview of the linked story.",
        "image_url": "https://example.com/articles/story.jpg",
    }
    return SocialLinkPreview(**(defaults | overrides))


def social_post(**overrides: Any) -> SocialPost:
    defaults: dict[str, Any] = {
        "text": "A useful update from Mark Johnson.",
        "source_url": "https://x.com/mark_johnson/status/123456789",
        "title": "Product update",
        "language": "en",
        "created_at": "2026-01-15T12:00:00Z",
        "embedded_post": None,
    }
    if "platform" not in overrides:
        defaults["platform"] = social_platform_brand()
    if "author" not in overrides:
        defaults["author"] = social_author()
    if "media" not in overrides:
        defaults["media"] = [social_media_item()]
    if "link_previews" not in overrides:
        defaults["link_previews"] = [social_link_preview()]
    return SocialPost(**(defaults | overrides))


def social_media_asset(**overrides: Any) -> SocialMediaAsset:
    defaults: dict[str, Any] = {
        "path": Path("test/fixtures/social-photo.jpg"),
    }
    if "media" not in overrides:
        defaults["media"] = social_media_item()
    return SocialMediaAsset(**(defaults | overrides))


def social_link_preview_asset(**overrides: Any) -> SocialLinkPreviewAsset:
    defaults: dict[str, Any] = {
        "og_image_path": Path("test/fixtures/social-link-preview.jpg"),
        "favicon_path": Path("test/fixtures/social-favicon.png"),
        "short_url": "example.com/story",
    }
    if "link_preview" not in overrides:
        defaults["link_preview"] = social_link_preview()
    return SocialLinkPreviewAsset(**(defaults | overrides))


def social_post_render_assets(**overrides: Any) -> SocialPostRenderAssets:
    defaults = {
        "avatar_path": Path("test/fixtures/social-avatar.jpg"),
        "media": [social_media_asset()],
        "link_previews": [social_link_preview_asset()],
        "embedded_post": None,
    }
    return SocialPostRenderAssets(**(defaults | overrides))


def social_media_placement(**overrides: Any) -> SocialMediaPlacement:
    defaults: dict[str, Any] = {
        "x": 40,
        "y": 240,
        "width": 1200,
        "height": 675,
        "top_left_radius": 24,
        "top_right_radius": 24,
        "bottom_right_radius": 24,
        "bottom_left_radius": 24,
    }
    if "media" not in overrides:
        defaults["media"] = social_media_item()
    return SocialMediaPlacement(**(defaults | overrides))


def social_card_video_input(**overrides: Any) -> SocialCardVideoInput:
    defaults: dict[str, Any] = {
        "media_path": Path("test/fixtures/social-video.mp4"),
    }
    if "placement" not in overrides:
        defaults["placement"] = social_media_placement(
            media = social_media_item(
                kind = SocialMediaKind.VIDEO,
                dynamic_media = social_dynamic_media(),
            ),
        )
    return SocialCardVideoInput(**(defaults | overrides))


def social_card_template_result(**overrides: Any) -> SocialCardTemplateResult:
    defaults = {
        "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
        "width": 1280,
        "height": 720,
        "media_placements": [],
    }
    return SocialCardTemplateResult(**(defaults | overrides))


def social_card_render_result(**overrides: Any) -> SocialCardRenderResult:
    defaults = {
        "public_url": "https://example.com/social-cards/card.png",
        "mode": SocialCardMode.IMAGE,
    }
    return SocialCardRenderResult(**(defaults | overrides))


def asset_price(**overrides: Any) -> AssetPrice:
    defaults = {
        "asset": "BTC",
        "asset_type": AssetType.crypto,
        "amount": 1.0,
        "currency": "USD",
        "unit_price": 50_000.0,
        "value": 50_000.0,
        "provider": "CoinMarketCap",
        "symbol": "BTC",
        "native_currency": "USD",
        "native_price": 50_000.0,
        "name": "Bitcoin",
        "exchange": None,
        "mic_code": None,
        "timestamp": 1_768_478_400,
        "is_market_open": None,
        "previous_close": None,
        "change": None,
        "percent_change": None,
    }
    return AssetPrice(**(defaults | overrides))


def stock_quote(**overrides: Any) -> StockQuote:
    defaults = {
        "symbol": "AAPL",
        "native_currency": "USD",
        "native_price": 250.0,
        "timestamp": 1_768_478_400,
        "is_market_open": True,
        "provider": "Twelve Data",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "mic_code": "XNAS",
        "previous_close": 248.0,
        "change": 2.0,
        "percent_change": 0.81,
        "requested_qualifier": None,
    }
    return StockQuote(**(defaults | overrides))
