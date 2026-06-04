from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from db.model.chat_config import ChatConfigDB
from db.schema.chat_config import ChatConfig
from db.schema.user import User
from util.config import config
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError

if TYPE_CHECKING:

    from google.genai import Client as GoogleSDKClient
    from langchain_core.documents import Document
    from openai import OpenAI
    from replicate.client import Client as ReplicateSDKClient
    from xai_sdk import Client as XAISDKClient

    from api.authorization_service import AuthorizationService
    from api.gumroad_controller import GumroadController
    from api.profile_connect_controller import ProfileConnectController
    from api.purchases_controller import PurchasesController
    from api.settings_controller import SettingsController
    from api.sponsorships_controller import SponsorshipsController
    from api.transfers_controller import TransfersController
    from api.usage_controller import UsageController
    from db.crud.chat_config import ChatConfigCRUD
    from db.crud.chat_message import ChatMessageCRUD
    from db.crud.chat_message_attachment import ChatMessageAttachmentCRUD
    from db.crud.price_alert import PriceAlertCRUD
    from db.crud.sponsorship import SponsorshipCRUD
    from db.crud.tools_cache import ToolsCacheCRUD
    from db.crud.user import UserCRUD
    from features.accounting.purchases.purchase_record_repo import PurchaseRecordRepository
    from features.accounting.purchases.purchase_service import PurchaseService
    from features.accounting.spending.spending_service import SpendingService
    from features.accounting.transfers.credit_transfer_service import CreditTransferService
    from features.accounting.usage.decorators.chat_model_usage_tracking_decorator import ChatModelUsageTrackingDecorator
    from features.accounting.usage.decorators.google_ai_usage_tracking_decorator import GoogleAIUsageTrackingDecorator
    from features.accounting.usage.decorators.google_search_usage_tracking_decorator import GoogleSearchUsageTrackingDecorator
    from features.accounting.usage.decorators.http_usage_tracking_decorator import HTTPUsageTrackingDecorator
    from features.accounting.usage.decorators.openai_usage_tracking_decorator import OpenAIUsageTrackingDecorator
    from features.accounting.usage.decorators.replicate_usage_tracking_decorator import ReplicateUsageTrackingDecorator
    from features.accounting.usage.decorators.web_fetcher_usage_tracking_decorator import WebFetcherUsageTrackingDecorator
    from features.accounting.usage.decorators.x_ai_usage_tracking_decorator import XAIUsageTrackingDecorator
    from features.accounting.usage.usage_record_repo import UsageRecordRepository
    from features.accounting.usage.usage_tracking_service import UsageTrackingService
    from features.announcements.release_summary_service import ReleaseSummaryService
    from features.announcements.sys_announcements_service import SysAnnouncementsService
    from features.audio.audio_transcriber import AudioTranscriber
    from features.chat.chat_agent import ChatAgent
    from features.chat.chat_attachment_processor import ChatAttachmentProcessor
    from features.chat.chat_image_edit_service import ChatImageEditService
    from features.chat.chat_progress_notifier import ChatProgressNotifier
    from features.chat.command_processor import CommandProcessor
    from features.chat.currency_alert_service import CurrencyAlertService
    from features.chat.dev_announcements_service import DevAnnouncementsService
    from features.chat.llm_tools.llm_tool_library import LLMToolLibrary
    from features.chat.membership.chat_membership_repo import ChatMembershipRepository
    from features.chat.membership.chat_membership_service import ChatMembershipService
    from features.chat.telegram.domain_langchain_mapper import DomainLangchainMapper
    from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
    from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
    from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
    from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
    from features.chat.url_attachment_resolver import UrlAttachmentResolver
    from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
    from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK
    from features.chat.whatsapp.whatsapp_data_resolver import WhatsAppDataResolver
    from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
    from features.cleanup.cleanup_service import CleanupService
    from features.connect.profile_connect_service import ProfileConnectService
    from features.currencies.exchange_rate_fetcher import ExchangeRateFetcher
    from features.documents.document_search import DocumentSearch
    from features.documents.langchain_embeddings_adapter import LangChainEmbeddingsAdapter
    from features.external_tools.access_token_resolver import AccessTokenResolver
    from features.external_tools.configured_tool import ConfiguredTool
    from features.external_tools.tool_choice_resolver import ToolChoiceResolver
    from features.images.computer_vision_analyzer import ComputerVisionAnalyzer
    from features.images.image_editor import ImageEditor
    from features.images.image_uploader import ImageUploader
    from features.images.simple_image_generator import SimpleImageGenerator
    from features.images.smart_image_generator import SmartImageGenerator
    from features.integrations.platform_bot_sdk import PlatformBotSDK
    from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
    from features.sponsorships.sponsorship_service import SponsorshipService
    from features.support.user_support_service import UserSupportService
    from features.web_browsing.ai_web_search import AIWebSearch
    from features.web_browsing.html_content_cleaner import HTMLContentCleaner
    from features.web_browsing.photo_downloader import PhotoDownloader
    from features.web_browsing.twitter_status_fetcher import TwitterStatusFetcher
    from features.web_browsing.url_shortener import UrlShortener
    from features.web_browsing.web_fetcher import WebFetcher
    from util.translations_cache import TranslationsCache


class DI:

    # Dynamic dependencies
    _db: Session | None
    _invoker_id: str | None
    _invoker_chat_id: str | None
    _invoker: User | None
    _invoker_chat: ChatConfig | None
    # SDKs
    _telegram_bot_api: "TelegramBotAPI | None"
    _whatsapp_bot_api: "WhatsAppBotAPI | None"
    _telegram_bot_sdk: "TelegramBotSDK | None"
    _whatsapp_bot_sdk: "WhatsAppBotSDK | None"
    # Repositories
    _user_crud: "UserCRUD | None"
    _chat_config_crud: "ChatConfigCRUD | None"
    _chat_membership_repo: "ChatMembershipRepository | None"
    _chat_membership_service: "ChatMembershipService | None"
    _chat_message_crud: "ChatMessageCRUD | None"
    _chat_message_attachment_crud: "ChatMessageAttachmentCRUD | None"
    _sponsorship_crud: "SponsorshipCRUD | None"
    _tools_cache_crud: "ToolsCacheCRUD | None"
    _price_alert_crud: "PriceAlertCRUD | None"
    _usage_record_repo: "UsageRecordRepository | None"
    _purchase_record_repo: "PurchaseRecordRepository | None"
    # Services
    _cleanup_service: "CleanupService | None"
    _sponsorship_service: "SponsorshipService | None"
    _credit_transfer_service: "CreditTransferService | None"
    _profile_connect_service: "ProfileConnectService | None"
    _authorization_service: "AuthorizationService | None"
    _usage_tracking_service: "UsageTrackingService | None"
    _purchase_service: "PurchaseService | None"
    _spending_service: "SpendingService | None"
    # Controllers
    _settings_controller: "SettingsController | None"
    _sponsorships_controller: "SponsorshipsController | None"
    _transfers_controller: "TransfersController | None"
    _usage_controller: "UsageController | None"
    _profile_connect_controller: "ProfileConnectController | None"
    _gumroad_controller: "GumroadController | None"
    _purchases_controller: "PurchasesController | None"
    # Internal tools
    _access_token_resolver: "AccessTokenResolver | None"
    _tool_choice_resolver: "ToolChoiceResolver | None"
    _domain_langchain_mapper: "DomainLangchainMapper | None"
    _telegram_domain_mapper: "TelegramDomainMapper | None"
    _whatsapp_domain_mapper: "WhatsAppDomainMapper | None"
    _telegram_data_resolver: "TelegramDataResolver | None"
    _whatsapp_data_resolver: "WhatsAppDataResolver | None"
    # Features & Dynamic Instances
    _llm_tool_library: "LLMToolLibrary | None"
    _command_processor: "CommandProcessor | None"
    _exchange_rate_fetcher: "ExchangeRateFetcher | None"

    def __init__(
        self,
        db: Session | None = None,
        invoker_id: str | None = None,
        invoker_chat_id: str | None = None,
    ):
        # Dynamic dependencies
        self._db = db
        self._invoker_id = invoker_id
        self._invoker_chat_id = invoker_chat_id
        self._invoker = None
        self._invoker_chat = None
        # SDKs
        self._telegram_bot_api = None
        self._whatsapp_bot_api = None
        self._telegram_bot_sdk = None
        self._whatsapp_bot_sdk = None
        # Repositories
        self._user_crud = None
        self._chat_config_crud = None
        self._chat_membership_repo = None
        self._chat_membership_service = None
        self._chat_message_crud = None
        self._chat_message_attachment_crud = None
        self._sponsorship_crud = None
        self._tools_cache_crud = None
        self._price_alert_crud = None
        self._usage_record_repo = None
        self._purchase_record_repo = None
        # Services
        self._cleanup_service = None
        self._sponsorship_service = None
        self._credit_transfer_service = None
        self._profile_connect_service = None
        self._authorization_service = None
        self._usage_tracking_service = None
        self._purchase_service = None
        self._spending_service = None
        # Controllers
        self._settings_controller = None
        self._sponsorships_controller = None
        self._transfers_controller = None
        self._usage_controller = None
        self._profile_connect_controller = None
        self._gumroad_controller = None
        self._purchases_controller = None
        # Internal tools
        self._access_token_resolver = None
        self._tool_choice_resolver = None
        self._domain_langchain_mapper = None
        self._telegram_domain_mapper = None
        self._whatsapp_domain_mapper = None
        self._telegram_data_resolver = None
        self._whatsapp_data_resolver = None
        # Features & Dynamic Instances
        self._llm_tool_library = None
        self._command_processor = None
        self._exchange_rate_fetcher = None

    # === Cloning ===

    def clone(
        self,
        db: Session | None = None,
        invoker_id: str | None = None,
        invoker_chat_id: str | None = None,
    ) -> "DI":
        return DI(
            db or self._db,
            invoker_id or self._invoker_id,
            invoker_chat_id or self._invoker_chat_id,
        )

    # === Dynamic dependencies ===

    @property
    def db(self) -> Session:
        if self._db is None:
            raise InternalError("Database session not provided", DI_DEPENDENCY_NOT_MET)
        return self._db

    @property
    def invoker_id(self) -> str:
        if self._invoker_id is None:
            raise InternalError("Invoker ID not provided", DI_DEPENDENCY_NOT_MET)
        return self._invoker_id

    @property
    def invoker_chat_id(self) -> str:
        if self._invoker_chat_id is None:
            raise InternalError("Invoker chat ID not provided", DI_DEPENDENCY_NOT_MET)
        return self._invoker_chat_id

    @property
    def invoker(self) -> User:
        if self._invoker is None:
            try:
                self._invoker = self.authorization_service.validate_user(self.invoker_id)
            except Exception as e:
                raise InternalError(f"Invoker validation failed: {e}", DI_DEPENDENCY_NOT_MET) from e
        return self._invoker

    @property
    def invoker_chat(self) -> ChatConfig | None:
        if self._invoker_chat_id is not None and self._invoker_chat is None:
            try:
                self._invoker_chat = self.authorization_service.validate_chat(self.invoker_chat_id)
            except Exception as e:
                raise InternalError(f"Invoker chat validation failed: {e}", DI_DEPENDENCY_NOT_MET) from e
        return self._invoker_chat

    @property
    def invoker_chat_type(self) -> ChatConfigDB.ChatType | None:
        if self.invoker_chat is not None:
            return self.invoker_chat.chat_type
        return None

    def require_invoker_chat(self) -> ChatConfig:
        if self.invoker_chat is None:
            raise InternalError("Chat context is required for this operation", DI_DEPENDENCY_NOT_MET)
        return self.invoker_chat

    def require_invoker_chat_type(self) -> ChatConfigDB.ChatType:
        if self.invoker_chat_type is None:
            raise InternalError("Chat type is required for this operation", DI_DEPENDENCY_NOT_MET)
        return self.invoker_chat_type

    # === Dynamic injections ===

    def inject_invoker_id(self, invoker_id: str | None):
        self._invoker_id = invoker_id
        if self._invoker and self._invoker.id.hex != invoker_id:
            self._invoker = None

    def inject_invoker(self, invoker: User | None):
        if not invoker:
            self._invoker = None
            self._invoker_id = None
            return
        self._invoker = invoker
        if not self._invoker_id or self._invoker_id != invoker.id:
            self._invoker_id = invoker.id.hex

    def inject_invoker_chat_id(self, invoker_chat_id: str | None):
        self._invoker_chat_id = invoker_chat_id
        if self._invoker_chat and self._invoker_chat.chat_id.hex != invoker_chat_id:
            self._invoker_chat = None

    def inject_invoker_chat(self, invoker_chat: ChatConfig | None):
        if not invoker_chat:
            self._invoker_chat = None
            self._invoker_chat_id = None
            return
        self._invoker_chat = invoker_chat
        if not self._invoker_chat_id or self._invoker_chat_id != invoker_chat.chat_id.hex:
            self._invoker_chat_id = invoker_chat.chat_id.hex

    # === SDKs ===

    @property
    def telegram_bot_api(self) -> "TelegramBotAPI":
        if self._telegram_bot_api is None:
            from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
            self._telegram_bot_api = TelegramBotAPI()
        return self._telegram_bot_api

    @property
    def whatsapp_bot_api(self) -> "WhatsAppBotAPI":
        if self._whatsapp_bot_api is None:
            from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
            self._whatsapp_bot_api = WhatsAppBotAPI()
        return self._whatsapp_bot_api

    @property
    def telegram_bot_sdk(self) -> "TelegramBotSDK":
        if self._telegram_bot_sdk is None:
            from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
            self._telegram_bot_sdk = TelegramBotSDK(self)
        return self._telegram_bot_sdk

    @property
    def whatsapp_bot_sdk(self) -> "WhatsAppBotSDK":
        if self._whatsapp_bot_sdk is None:
            from features.chat.whatsapp.sdk.whatsapp_bot_sdk import WhatsAppBotSDK
            self._whatsapp_bot_sdk = WhatsAppBotSDK(self)
        return self._whatsapp_bot_sdk

    # === Repositories ===

    @property
    def user_crud(self) -> "UserCRUD":
        if self._user_crud is None:
            from db.crud.user import UserCRUD
            self._user_crud = UserCRUD(self.db)
        return self._user_crud

    @property
    def chat_config_crud(self) -> "ChatConfigCRUD":
        if self._chat_config_crud is None:
            from db.crud.chat_config import ChatConfigCRUD
            self._chat_config_crud = ChatConfigCRUD(self.db)
        return self._chat_config_crud

    @property
    def chat_membership_repo(self) -> "ChatMembershipRepository":
        if self._chat_membership_repo is None:
            from features.chat.membership.chat_membership_repo import ChatMembershipRepository
            self._chat_membership_repo = ChatMembershipRepository(self.db)
        return self._chat_membership_repo

    @property
    def chat_membership_service(self) -> "ChatMembershipService":
        if self._chat_membership_service is None:
            from features.chat.membership.chat_membership_service import ChatMembershipService
            self._chat_membership_service = ChatMembershipService(self)
        return self._chat_membership_service

    @property
    def chat_message_crud(self) -> "ChatMessageCRUD":
        if self._chat_message_crud is None:
            from db.crud.chat_message import ChatMessageCRUD
            self._chat_message_crud = ChatMessageCRUD(self.db)
        return self._chat_message_crud

    @property
    def chat_message_attachment_crud(self) -> "ChatMessageAttachmentCRUD":
        if self._chat_message_attachment_crud is None:
            from db.crud.chat_message_attachment import ChatMessageAttachmentCRUD
            self._chat_message_attachment_crud = ChatMessageAttachmentCRUD(self.db)
        return self._chat_message_attachment_crud

    @property
    def sponsorship_crud(self) -> "SponsorshipCRUD":
        if self._sponsorship_crud is None:
            from db.crud.sponsorship import SponsorshipCRUD
            self._sponsorship_crud = SponsorshipCRUD(self.db)
        return self._sponsorship_crud

    @property
    def tools_cache_crud(self) -> "ToolsCacheCRUD":
        if self._tools_cache_crud is None:
            from db.crud.tools_cache import ToolsCacheCRUD
            self._tools_cache_crud = ToolsCacheCRUD(self.db)
        return self._tools_cache_crud

    @property
    def price_alert_crud(self) -> "PriceAlertCRUD":
        if self._price_alert_crud is None:
            from db.crud.price_alert import PriceAlertCRUD
            self._price_alert_crud = PriceAlertCRUD(self.db)
        return self._price_alert_crud

    @property
    def usage_record_repo(self) -> "UsageRecordRepository":
        if self._usage_record_repo is None:
            from features.accounting.usage.usage_record_repo import UsageRecordRepository
            self._usage_record_repo = UsageRecordRepository(self.db)
        return self._usage_record_repo

    @property
    def purchase_record_repo(self) -> "PurchaseRecordRepository":
        if self._purchase_record_repo is None:
            from features.accounting.purchases.purchase_record_repo import PurchaseRecordRepository
            self._purchase_record_repo = PurchaseRecordRepository(self.db)
        return self._purchase_record_repo

    # === Services ===

    @property
    def cleanup_service(self) -> "CleanupService":
        if self._cleanup_service is None:
            from features.cleanup.cleanup_service import CleanupService
            self._cleanup_service = CleanupService(self)
        return self._cleanup_service

    @property
    def sponsorship_service(self) -> "SponsorshipService":
        if self._sponsorship_service is None:
            from features.sponsorships.sponsorship_service import SponsorshipService
            self._sponsorship_service = SponsorshipService(self)
        return self._sponsorship_service

    @property
    def credit_transfer_service(self) -> "CreditTransferService":
        if self._credit_transfer_service is None:
            from features.accounting.transfers.credit_transfer_service import CreditTransferService
            self._credit_transfer_service = CreditTransferService(self)
        return self._credit_transfer_service

    @property
    def authorization_service(self) -> "AuthorizationService":
        if self._authorization_service is None:
            from api.authorization_service import AuthorizationService
            self._authorization_service = AuthorizationService(self)
        return self._authorization_service

    @property
    def usage_tracking_service(self) -> "UsageTrackingService":
        if self._usage_tracking_service is None:
            from features.accounting.usage.usage_tracking_service import UsageTrackingService
            self._usage_tracking_service = UsageTrackingService(self)
        return self._usage_tracking_service

    @property
    def profile_connect_service(self) -> "ProfileConnectService":
        if self._profile_connect_service is None:
            from features.connect.profile_connect_service import ProfileConnectService
            self._profile_connect_service = ProfileConnectService(self)
        return self._profile_connect_service

    @property
    def purchase_service(self) -> "PurchaseService":
        if self._purchase_service is None:
            from features.accounting.purchases.purchase_service import PurchaseService
            self._purchase_service = PurchaseService(self)
        return self._purchase_service

    @property
    def spending_service(self) -> "SpendingService":
        if self._spending_service is None:
            from features.accounting.spending.spending_service import SpendingService
            self._spending_service = SpendingService(self)
        return self._spending_service

    # === Controllers ===

    @property
    def settings_controller(self) -> "SettingsController":
        if self._settings_controller is None:
            from api.settings_controller import SettingsController
            self._settings_controller = SettingsController(self)
        return self._settings_controller

    @property
    def sponsorships_controller(self) -> "SponsorshipsController":
        if self._sponsorships_controller is None:
            from api.sponsorships_controller import SponsorshipsController
            self._sponsorships_controller = SponsorshipsController(self)
        return self._sponsorships_controller

    @property
    def transfers_controller(self) -> "TransfersController":
        if self._transfers_controller is None:
            from api.transfers_controller import TransfersController
            self._transfers_controller = TransfersController(self)
        return self._transfers_controller

    @property
    def usage_controller(self) -> "UsageController":
        if self._usage_controller is None:
            from api.usage_controller import UsageController
            self._usage_controller = UsageController(self)
        return self._usage_controller

    @property
    def profile_connect_controller(self) -> "ProfileConnectController":
        if self._profile_connect_controller is None:
            from api.profile_connect_controller import ProfileConnectController
            self._profile_connect_controller = ProfileConnectController(self)
        return self._profile_connect_controller

    @property
    def gumroad_controller(self) -> "GumroadController":
        if self._gumroad_controller is None:
            from api.gumroad_controller import GumroadController
            self._gumroad_controller = GumroadController(self)
        return self._gumroad_controller

    @property
    def purchases_controller(self) -> "PurchasesController":
        if self._purchases_controller is None:
            from api.purchases_controller import PurchasesController
            self._purchases_controller = PurchasesController(self)
        return self._purchases_controller

    # === Internal tools ===

    @property
    def access_token_resolver(self) -> "AccessTokenResolver":
        if self._access_token_resolver is None:
            from features.external_tools.access_token_resolver import AccessTokenResolver
            self._access_token_resolver = AccessTokenResolver(self)
        return self._access_token_resolver

    @property
    def tool_choice_resolver(self) -> "ToolChoiceResolver":
        if self._tool_choice_resolver is None:
            from features.external_tools.tool_choice_resolver import ToolChoiceResolver
            self._tool_choice_resolver = ToolChoiceResolver(self)
        return self._tool_choice_resolver

    @property
    def translations_cache(self) -> "TranslationsCache":
        from util.translations_cache import TranslationsCache
        return TranslationsCache()

    @property
    def domain_langchain_mapper(self) -> "DomainLangchainMapper":
        if self._domain_langchain_mapper is None:
            from features.chat.telegram.domain_langchain_mapper import DomainLangchainMapper
            self._domain_langchain_mapper = DomainLangchainMapper()
        return self._domain_langchain_mapper

    @property
    def telegram_domain_mapper(self) -> "TelegramDomainMapper":
        if self._telegram_domain_mapper is None:
            from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
            self._telegram_domain_mapper = TelegramDomainMapper()
        return self._telegram_domain_mapper

    @property
    def whatsapp_domain_mapper(self) -> "WhatsAppDomainMapper":
        if self._whatsapp_domain_mapper is None:
            from features.chat.whatsapp.whatsapp_domain_mapper import WhatsAppDomainMapper
            self._whatsapp_domain_mapper = WhatsAppDomainMapper()
        return self._whatsapp_domain_mapper

    @property
    def telegram_data_resolver(self) -> "TelegramDataResolver":
        if self._telegram_data_resolver is None:
            from features.chat.telegram.telegram_data_resolver import TelegramDataResolver
            self._telegram_data_resolver = TelegramDataResolver(self)
        return self._telegram_data_resolver

    @property
    def whatsapp_data_resolver(self) -> "WhatsAppDataResolver":
        if self._whatsapp_data_resolver is None:
            from features.chat.whatsapp.whatsapp_data_resolver import WhatsAppDataResolver
            self._whatsapp_data_resolver = WhatsAppDataResolver(self)
        return self._whatsapp_data_resolver

    # === Features & Dynamic Instances ===

    def chat_langchain_model(
        self,
        configured_tool: ConfiguredTool,
    ) -> "ChatModelUsageTrackingDecorator":
        from features.accounting.usage.decorators.chat_model_usage_tracking_decorator import ChatModelUsageTrackingDecorator
        from features.llm import langchain_creator

        resolved_max_tokens = self.__resolve_max_output_tokens(configured_tool)
        base_model = langchain_creator.create(configured_tool, resolved_max_tokens)
        return ChatModelUsageTrackingDecorator(
            base_model,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
            resolved_max_tokens,
        )

    def base_replicate_client(self, api_token: str, timeout_s: float | None = None) -> "ReplicateSDKClient":
        from httpx import Timeout
        from replicate.client import Client as ReplicateSDKClient

        return ReplicateSDKClient(
            api_token = api_token,
            timeout = Timeout(timeout_s) if timeout_s is not None else None,
        )

    def replicate_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
    ) -> "ReplicateUsageTrackingDecorator":
        from features.accounting.usage.decorators.replicate_usage_tracking_decorator import ReplicateUsageTrackingDecorator

        base_client = self.base_replicate_client(configured_tool.token.get_secret_value(), timeout_s)
        return ReplicateUsageTrackingDecorator(
            base_client,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
            output_image_sizes,
            input_image_sizes,
        )

    def base_google_ai_client(
        self,
        api_key: str,
        timeout_s: float | None = None,
    ) -> "GoogleSDKClient":
        from google.genai import Client as GoogleSDKClient
        from google.genai.types import HttpOptions

        http_options: HttpOptions | None = None
        if timeout_s is not None:
            http_options = HttpOptions(timeout = int(timeout_s * 1000))
        return GoogleSDKClient(api_key = api_key, http_options = http_options)

    def google_ai_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
    ) -> "GoogleAIUsageTrackingDecorator":
        from features.accounting.usage.decorators.google_ai_usage_tracking_decorator import GoogleAIUsageTrackingDecorator

        base_client = self.base_google_ai_client(configured_tool.token.get_secret_value(), timeout_s)
        return GoogleAIUsageTrackingDecorator(
            base_client,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
            output_image_sizes,
            input_image_sizes,
        )

    def google_search_client(
        self,
        configured_tool: ConfiguredTool,
    ) -> "GoogleSearchUsageTrackingDecorator":
        from features.accounting.usage.decorators.google_search_usage_tracking_decorator import GoogleSearchUsageTrackingDecorator

        base_client = self.base_google_ai_client(configured_tool.token.get_secret_value(), config.web_timeout_s * 6)
        return GoogleSearchUsageTrackingDecorator(
            base_client,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
        )

    def base_x_ai_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
    ) -> "XAISDKClient":
        from xai_sdk import Client as XAISDKClient

        return XAISDKClient(api_key = configured_tool.token.get_secret_value(), timeout = timeout_s)

    def x_ai_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
        output_image_sizes: list[str] | None = None,
        input_image_sizes: list[str] | None = None,
    ) -> "XAIUsageTrackingDecorator":
        from features.accounting.usage.decorators.x_ai_usage_tracking_decorator import XAIUsageTrackingDecorator

        base_client = self.base_x_ai_client(configured_tool, timeout_s)
        return XAIUsageTrackingDecorator(
            base_client,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
            output_image_sizes,
            input_image_sizes,
        )

    def base_open_ai_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
    ) -> "OpenAI":
        from openai import OpenAI

        return OpenAI(api_key = configured_tool.token.get_secret_value(), timeout = timeout_s)

    def open_ai_client(
        self,
        configured_tool: ConfiguredTool,
        timeout_s: float | None = None,
    ) -> "OpenAIUsageTrackingDecorator":
        from features.accounting.usage.decorators.openai_usage_tracking_decorator import OpenAIUsageTrackingDecorator

        base_client = self.base_open_ai_client(configured_tool, timeout_s)
        return OpenAIUsageTrackingDecorator(
            base_client,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
        )

    def openai_embeddings(self, configured_tool: ConfiguredTool) -> "LangChainEmbeddingsAdapter":
        from features.documents.langchain_embeddings_adapter import LangChainEmbeddingsAdapter

        client = self.open_ai_client(configured_tool)
        return LangChainEmbeddingsAdapter(client, configured_tool.definition.id)

    def tracked_http_get(self, configured_tool: ConfiguredTool) -> "HTTPUsageTrackingDecorator":
        from features.accounting.usage.decorators.http_usage_tracking_decorator import HTTPUsageTrackingDecorator

        return HTTPUsageTrackingDecorator(
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
        )

    @property
    def llm_tool_library(self) -> "LLMToolLibrary":
        if self._llm_tool_library is None:
            from features.chat.llm_tools.llm_tool_library import LLMToolLibrary
            self._llm_tool_library = LLMToolLibrary(self)
        return self._llm_tool_library

    def platform_bot_sdk(self) -> "PlatformBotSDK":
        from features.integrations.platform_bot_sdk import PlatformBotSDK
        return PlatformBotSDK(di = self)

    def chat_progress_notifier(
        self,
        message_id: str,
        auto_start: bool = False,
    ) -> "ChatProgressNotifier":
        from features.chat.chat_progress_notifier import ChatProgressNotifier
        return ChatProgressNotifier(message_id, self, auto_start)

    @property
    def command_processor(self) -> "CommandProcessor":
        if self._command_processor is None:
            from features.chat.command_processor import CommandProcessor
            self._command_processor = CommandProcessor(self)
        return self._command_processor

    def chat_agent(
        self,
        raw_last_message: str,
        last_message_id: str,
        configured_tool: ConfiguredTool | None,
    ) -> "ChatAgent":
        from features.chat.chat_agent import ChatAgent
        return ChatAgent(raw_last_message, last_message_id, configured_tool, self)

    def web_fetcher(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cache_ttl_html: timedelta | None = None,
        cache_ttl_json: timedelta | None = None,
        auto_fetch_html: bool = False,
        auto_fetch_json: bool = False,
    ) -> "WebFetcher":
        from features.web_browsing.web_fetcher import WebFetcher
        return WebFetcher(
            url, self,
            headers, params,
            cache_ttl_html, cache_ttl_json,
            auto_fetch_html, auto_fetch_json,
        )

    def tracked_web_fetcher(
        self,
        configured_tool: ConfiguredTool,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cache_ttl_html: timedelta | None = None,
        cache_ttl_json: timedelta | None = None,
        auto_fetch_html: bool = False,
        auto_fetch_json: bool = False,
    ) -> "WebFetcherUsageTrackingDecorator":
        from features.accounting.usage.decorators.web_fetcher_usage_tracking_decorator import WebFetcherUsageTrackingDecorator

        base_fetcher = self.web_fetcher(
            url, headers, params,
            cache_ttl_html, cache_ttl_json,
            auto_fetch_html, auto_fetch_json,
        )
        return WebFetcherUsageTrackingDecorator(
            base_fetcher,
            self.usage_tracking_service,
            self.spending_service,
            configured_tool,
        )

    def html_content_cleaner(self, raw_html: str) -> "HTMLContentCleaner":
        from features.web_browsing.html_content_cleaner import HTMLContentCleaner
        return HTMLContentCleaner(raw_html, self)

    def twitter_status_fetcher(
        self,
        tweet_id: str,
        x_api_tool: ConfiguredTool,
        vision_tool: ConfiguredTool,
    ) -> "TwitterStatusFetcher":
        from features.web_browsing.twitter_status_fetcher import TwitterStatusFetcher
        return TwitterStatusFetcher(tweet_id, x_api_tool, vision_tool, self)

    # noinspection PyMethodMayBeStatic
    def photo_downloader(self, bearer_token: str | None = None) -> "PhotoDownloader":
        from features.web_browsing.photo_downloader import PhotoDownloader
        return PhotoDownloader(bearer_token = bearer_token)

    # noinspection PyMethodMayBeStatic
    def social_card_orchestrator(self, x_api_tool: ConfiguredTool) -> "SocialCardOrchestrator":
        from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
        return SocialCardOrchestrator(x_api_tool, self)

    def url_shortener(
        self,
        long_url: str,
        custom_slug: str | None = None,
        valid_until: datetime | None = None,
        max_visits: int | None = None,
    ) -> "UrlShortener":
        from features.web_browsing.url_shortener import UrlShortener
        return UrlShortener(long_url, custom_slug, valid_until, max_visits)

    @property
    def exchange_rate_fetcher(self) -> "ExchangeRateFetcher":
        if self._exchange_rate_fetcher is None:
            from features.currencies.exchange_rate_fetcher import ExchangeRateFetcher
            self._exchange_rate_fetcher = ExchangeRateFetcher(self)
        return self._exchange_rate_fetcher

    # noinspection PyMethodMayBeStatic
    def ai_web_search(self, search_query: str, configured_tool: ConfiguredTool) -> "AIWebSearch":
        from features.web_browsing.ai_web_search import AIWebSearch
        return AIWebSearch(search_query, configured_tool, self)

    def currency_alert_service(self, target_chat_id: str | None) -> "CurrencyAlertService":
        from features.chat.currency_alert_service import CurrencyAlertService
        return CurrencyAlertService(target_chat_id, self)

    def smart_image_generator(
        self,
        raw_prompt: str,
        configured_copywriter_tool: ConfiguredTool,
        configured_image_gen_tool: ConfiguredTool,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ) -> "SmartImageGenerator":
        from features.images.smart_image_generator import SmartImageGenerator
        return SmartImageGenerator(
            raw_prompt, configured_copywriter_tool, configured_image_gen_tool, self, aspect_ratio, output_size,
        )

    # noinspection PyMethodMayBeStatic
    def simple_image_generator(
        self,
        prompt: str,
        configured_tool: ConfiguredTool,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ) -> "SimpleImageGenerator":
        from features.images.simple_image_generator import SimpleImageGenerator
        return SimpleImageGenerator(prompt, configured_tool, self, aspect_ratio, output_size)

    # noinspection PyMethodMayBeStatic
    def image_uploader(
        self,
        binary_image: bytes | None = None,
        base64_image: str | None = None,
        expiration_s: int | None = None,
        name: str | None = None,
    ) -> "ImageUploader":
        from features.images.image_uploader import ImageUploader
        return ImageUploader(binary_image, base64_image, expiration_s, name)

    # noinspection PyMethodMayBeStatic
    def file_uploader(
        self,
        content: bytes,
        filename: str,
    ):
        from features.files.file_uploader import FileUploader
        return FileUploader(content, filename)

    def chat_image_edit_service(
        self,
        attachment_ids: list[str] | None,
        urls: list[str] | None = None,
        operation_guidance: str | None = None,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ) -> "ChatImageEditService":
        from features.chat.chat_image_edit_service import ChatImageEditService
        return ChatImageEditService(attachment_ids, urls, operation_guidance, aspect_ratio, output_size, self)

    def image_editor(
        self,
        image_urls: list[str],
        configured_tool: ConfiguredTool,
        prompt: str,
        input_mime_types: list[str | None],
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ) -> "ImageEditor":
        from features.images.image_editor import ImageEditor
        return ImageEditor(image_urls, configured_tool, prompt, self, input_mime_types, aspect_ratio, output_size)

    def computer_vision_analyzer(
        self,
        job_id: str,
        image_mime_types: list[str],
        configured_tool: ConfiguredTool,
        image_urls: list[str] | None = None,
        image_b64s: list[str] | None = None,
        additional_context: str | None = None,
    ) -> "ComputerVisionAnalyzer":
        from features.images.computer_vision_analyzer import ComputerVisionAnalyzer
        return ComputerVisionAnalyzer(job_id, image_mime_types, configured_tool, self, image_urls, image_b64s, additional_context)

    # noinspection PyMethodMayBeStatic
    def plain_text_loader(self, job_id: str, document_url: str):
        from features.documents.plain_text_loader import PlainTextLoader
        return PlainTextLoader(job_id, document_url)

    # noinspection PyMethodMayBeStatic
    def docx_loader(self, job_id: str, document_url: str):
        from features.documents.docx_loader import DocxLoader
        return DocxLoader(job_id, document_url)

    # noinspection PyMethodMayBeStatic
    def pdf_loader(self, job_id: str, document_url: str):
        from features.documents.pdf_loader import PdfLoader
        return PdfLoader(job_id, document_url)

    def document_search(
        self,
        job_id: str,
        documents: list[Document],
        embedding_tool: ConfiguredTool,
        copywriter_tool: ConfiguredTool,
        additional_context: str | None = None,
    ) -> "DocumentSearch":
        from features.documents.document_search import DocumentSearch
        return DocumentSearch(job_id, documents, embedding_tool, copywriter_tool, self, additional_context)

    def audio_transcriber(
        self,
        job_id: str,
        audio_url: str,
        transcriber_tool: ConfiguredTool,
        copywriter_tool: ConfiguredTool,
        def_extension: str | None = None,
        audio_content: bytes | None = None,
    ) -> "AudioTranscriber":
        from features.audio.audio_transcriber import AudioTranscriber
        return AudioTranscriber(
            job_id, audio_url,
            transcriber_tool, copywriter_tool, self,
            def_extension, audio_content,
        )

    def url_attachment_resolver(self, url: str) -> "UrlAttachmentResolver":
        from features.chat.url_attachment_resolver import UrlAttachmentResolver
        return UrlAttachmentResolver(url, self)

    def chat_attachment_processor(
        self,
        additional_context: str | None,
        attachment_ids: list[str] | None,
        urls: list[str] | None,
    ) -> "ChatAttachmentProcessor":
        from features.chat.chat_attachment_processor import ChatAttachmentProcessor
        return ChatAttachmentProcessor(additional_context, attachment_ids, urls, self)

    def dev_announcements_service(
        self,
        raw_message: str,
        target_handle: str | None,
        configured_tool: ConfiguredTool,
    ) -> "DevAnnouncementsService":
        from features.chat.dev_announcements_service import DevAnnouncementsService
        return DevAnnouncementsService(raw_message, target_handle, configured_tool, self)

    def sys_announcements_service(
        self,
        raw_information: str,
        target_chat: ChatConfig | None,
        configured_tool: ConfiguredTool,
    ) -> "SysAnnouncementsService":
        from features.announcements.sys_announcements_service import SysAnnouncementsService
        return SysAnnouncementsService(raw_information, target_chat, configured_tool, self)

    def release_summary_service(
        self,
        raw_notes: str,
        target_chat: ChatConfig | None,
        configured_tool: ConfiguredTool,
    ) -> "ReleaseSummaryService":
        from features.announcements.release_summary_service import ReleaseSummaryService
        return ReleaseSummaryService(raw_notes, target_chat, configured_tool, self)

    def user_support_service(
        self,
        user_input: str,
        github_author: str | None,
        include_platform_handle: bool,
        include_full_name: bool,
        request_type_str: str | None,
        configured_tool: ConfiguredTool,
    ) -> "UserSupportService":
        from features.support.user_support_service import UserSupportService
        return UserSupportService(
            user_input, github_author,
            include_platform_handle, include_full_name,
            request_type_str, configured_tool, self,
        )

    # === Private Helpers ===

    def __resolve_max_output_tokens(self, configured_tool: ConfiguredTool) -> int:
        multiplier = configured_tool.purpose.output_token_multiplier
        if self._invoker is not None and self._invoker_chat is not None:
            membership = self.chat_membership_service.get(self._invoker.id, self._invoker_chat.chat_id)
            if membership is not None:
                return int(membership.max_output_tokens * multiplier)
        return int(config.default_max_output_tokens * multiplier)
