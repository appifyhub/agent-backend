# ruff: noqa: E501

import logging
import os
from dataclasses import dataclass
from typing import Callable

import yaml
from pydantic import SecretStr

from util.singleton import Singleton


@dataclass(frozen = True)
class ConfiguredProduct:
    id: str
    credits: int
    name: str
    url: str


# don't forget to cover in test_config.py
class Config(metaclass = Singleton):

    DEV_API_KEY = "0000-1234-5678-0000"  # needed for local dev mode

    max_sponsorships_per_user: int
    log_level: str
    log_telegram_update: bool
    log_whatsapp_update: bool
    web_retries: int
    web_retry_delay_s: int
    web_timeout_s: int
    max_users: int
    default_max_output_tokens: int
    website_url: str
    parent_organization: str
    agent_bot_name: str
    background_bot_name: str
    background_bot_username: str
    github_bot_username: str
    github_bot_id: int
    telegram_bot_username: str
    telegram_bot_id: int
    telegram_api_base_url: str
    telegram_must_auth: bool
    whatsapp_must_auth: bool
    gumroad_must_auth: bool
    gumroad_seller_id_check: bool
    gumroad_seller_id: str
    whatsapp_phone_number_id: str
    whatsapp_bot_phone_number: str
    chat_history_depth: int
    chat_debounce_delay_s: float
    cleanup_message_retention_days: int
    cleanup_price_alert_staleness_days: int
    cleanup_sponsorship_staleness_days: int
    github_issues_repo: str
    issue_templates_abs_path: str
    jwt_expires_in_minutes: int
    backoffice_url_base: str
    public_api_base_url: str
    main_language_name: str = "English"
    main_language_iso_code: str = "en"
    uploadcare_public_key: str
    uploadcare_cdn_id: str
    url_shortener_base_url: str
    version: str
    usage_maintenance_fee_credits: float
    products_config_path: str
    products: dict[str, ConfiguredProduct]
    logos_config_path: str
    logos: dict[str, str]
    fonts_dir: str
    s3_base_url: str
    s3_region: str
    s3_bucket: str
    attachment_public_token_ttl_seconds: int

    platform_open_ai_key: SecretStr
    platform_anthropic_key: SecretStr
    platform_google_ai_key: SecretStr
    platform_perplexity_key: SecretStr
    platform_replicate_key: SecretStr
    platform_rapid_api_key: SecretStr
    platform_coinmarketcap_key: SecretStr
    platform_x_key: SecretStr
    platform_x_ai_key: SecretStr

    db_url: SecretStr
    api_key: SecretStr
    telegram_auth_key: SecretStr
    telegram_bot_token: SecretStr
    whatsapp_auth_key: SecretStr
    whatsapp_app_secret: SecretStr
    whatsapp_bot_token: SecretStr
    gumroad_auth_key: SecretStr
    jwt_secret_key: SecretStr
    github_issues_token: SecretStr
    free_img_host_token: SecretStr
    token_encrypt_secret: SecretStr
    uploadcare_private_key: SecretStr
    url_shortener_api_key: SecretStr
    s3_access_key: SecretStr
    s3_secret_key: SecretStr

    def all_secrets(self) -> list[SecretStr]:
        return [
            self.db_url,
            self.api_key,
            self.telegram_auth_key,
            self.telegram_bot_token,
            self.whatsapp_auth_key,
            self.whatsapp_app_secret,
            self.whatsapp_bot_token,
            self.gumroad_auth_key,
            self.jwt_secret_key,
            self.github_issues_token,
            self.free_img_host_token,
            self.token_encrypt_secret,
            self.uploadcare_private_key,
            self.url_shortener_api_key,
            self.platform_open_ai_key,
            self.platform_anthropic_key,
            self.platform_google_ai_key,
            self.platform_perplexity_key,
            self.platform_replicate_key,
            self.platform_rapid_api_key,
            self.platform_coinmarketcap_key,
            self.platform_x_key,
            self.platform_x_ai_key,
            self.s3_access_key,
            self.s3_secret_key,
        ]

    def __init__(
        self,
        def_max_sponsorships_per_user: int = 2,
        def_log_level: str = "INFO",
        def_log_telegram_update: bool = False,
        def_log_whatsapp_update: bool = False,
        def_web_retries: int = 3,
        def_web_retry_delay_s: int = 1,
        def_web_timeout_s: int = 10,
        def_max_users: int = 100,
        def_default_max_output_tokens: int = 3500,
        def_website_url: str = "https://agent.appifyhub.com",
        def_parent_organization: str = "AppifyHub",
        def_agent_bot_name: str = "The Agent",
        def_background_bot_name: str = "The Agent's Pulse",
        def_background_bot_username: str = "the_agent_pulse",
        def_github_bot_username: str = "the-agent",
        def_github_bot_id: int = 1234567890,
        def_telegram_bot_username: str = "the_agent",
        def_telegram_bot_id: int = 1234567890,
        def_telegram_api_base_url: str = "https://api.telegram.org",
        def_telegram_must_auth: bool = False,
        def_whatsapp_must_auth: bool = False,
        def_gumroad_must_auth: bool = False,
        def_gumroad_seller_id_check: bool = False,
        def_gumroad_seller_id: str = "invalid",
        def_whatsapp_phone_number_id: str = "invalid",
        def_whatsapp_bot_phone_number: str = "11234567890",
        def_chat_history_depth: int = 30,
        def_chat_debounce_delay_s: float = 1.0,
        def_cleanup_message_retention_days: int = 30,
        def_cleanup_price_alert_staleness_days: int = 360,
        def_cleanup_sponsorship_staleness_days: int = 30,
        def_github_issues_repo: str = "appifyhub/agent-backend",
        def_issue_templates_path: str = ".github/ISSUE_TEMPLATE",
        def_jwt_expires_in_minutes: int = 30,
        def_backoffice_url_base: str = "http://localhost:5173",
        def_public_api_base_url: str = "http://localhost:80",
        def_main_language_name: str = "English",
        def_main_language_iso_code: str = "en",
        def_uploadcare_public_key: str = "invalid",
        def_uploadcare_cdn_id: str = "invalid",
        def_url_shortener_base_url: str = "https://urls.appifyhub.com",
        def_version: str = "dev",
        def_usage_maintenance_fee_credits: float = 0.0,
        def_products_config_path: str = "config/products.yaml",
        def_logos_config_path: str = "config/logos.yaml",
        def_fonts_dir: str = "src/assets/fonts",
        def_s3_base_url: str = "",  # if not set, uses the local disk
        def_s3_region: str = "eu-central-1",
        def_s3_bucket: str = "the-agent",
        def_attachment_public_token_ttl_seconds: int = 600,
        def_platform_open_ai_key: SecretStr = SecretStr("invalid"),
        def_platform_anthropic_key: SecretStr = SecretStr("invalid"),
        def_platform_google_ai_key: SecretStr = SecretStr("invalid"),
        def_platform_perplexity_key: SecretStr = SecretStr("invalid"),
        def_platform_replicate_key: SecretStr = SecretStr("invalid"),
        def_platform_rapid_api_key: SecretStr = SecretStr("invalid"),
        def_platform_coinmarketcap_key: SecretStr = SecretStr("invalid"),
        def_platform_x_key: SecretStr = SecretStr("invalid"),
        def_platform_x_ai_key: SecretStr = SecretStr("invalid"),
        def_db_user: SecretStr = SecretStr("root"),
        def_db_pass: SecretStr = SecretStr("root"),
        def_db_host: SecretStr = SecretStr("localhost"),
        def_db_name: SecretStr = SecretStr("agent"),
        def_api_key: SecretStr = SecretStr(DEV_API_KEY),
        def_telegram_auth_key: SecretStr = SecretStr("it_is_really_telegram"),
        def_telegram_bot_token: SecretStr = SecretStr("invalid"),
        def_whatsapp_auth_key: SecretStr = SecretStr("it_is_really_whatsapp"),
        def_whatsapp_app_secret: SecretStr = SecretStr("invalid"),
        def_whatsapp_bot_token: SecretStr = SecretStr("invalid"),
        def_gumroad_auth_key: SecretStr = SecretStr("it_is_really_gumroad"),
        def_jwt_secret_key: SecretStr = SecretStr("default"),
        def_github_issues_token: SecretStr = SecretStr("invalid"),
        def_free_img_host_token: SecretStr = SecretStr("invalid"),
        def_token_encrypt_secret: SecretStr = SecretStr("default"),
        def_uploadcare_private_key: SecretStr = SecretStr("invalid"),
        def_url_shortener_api_key: SecretStr = SecretStr("invalid"),
        def_s3_access_key: SecretStr = SecretStr("local"),
        def_s3_secret_key: SecretStr = SecretStr("invalid"),
    ):
        # @formatter:off
        self.max_sponsorships_per_user = int(self.__env("MAX_SPONSORSHIPS_PER_USER", lambda: str(def_max_sponsorships_per_user)))
        self.log_level = self.__env("LOG_LEVEL", lambda: def_log_level).lower()
        self.log_telegram_update = self.__env("LOG_TG_UPDATE", lambda: str(def_log_telegram_update)).lower() == "true"
        self.log_whatsapp_update = self.__env("LOG_WA_UPDATE", lambda: str(def_log_whatsapp_update)).lower() == "true"
        self.web_retries = int(self.__env("WEB_RETRIES", lambda: str(def_web_retries)))
        self.web_retry_delay_s = int(self.__env("WEB_RETRY_DELAY_S", lambda: str(def_web_retry_delay_s)))
        self.web_timeout_s = int(self.__env("WEB_TIMEOUT_S", lambda: str(def_web_timeout_s)))
        self.max_users = int(self.__env("MAX_USERS", lambda: str(def_max_users)))
        self.default_max_output_tokens = int(self.__env("DEFAULT_MAX_OUTPUT_TOKENS", lambda: str(def_default_max_output_tokens)))
        self.website_url = self.__env("WEBSITE_URL", lambda: def_website_url)
        self.parent_organization = self.__env("PARENT_ORGANIZATION", lambda: def_parent_organization)
        self.agent_bot_name = self.__env("AGENT_BOT_NAME", lambda: def_agent_bot_name)
        self.background_bot_name = self.__env("BACKGROUND_BOT_NAME", lambda: def_background_bot_name)
        self.background_bot_username = self.__env("BACKGROUND_BOT_USERNAME", lambda: def_background_bot_username)
        self.github_bot_username = self.__env("GITHUB_BOT_USERNAME", lambda: def_github_bot_username)
        self.github_bot_id = int(self.__env("GITHUB_BOT_ID", lambda: str(def_github_bot_id)))
        self.telegram_bot_username = self.__env("TELEGRAM_BOT_USERNAME", lambda: def_telegram_bot_username)
        self.telegram_bot_id = int(self.__env("TELEGRAM_BOT_ID", lambda: str(def_telegram_bot_id)))
        self.telegram_api_base_url = self.__env("TELEGRAM_API_BASE_URL", lambda: def_telegram_api_base_url)
        self.telegram_must_auth = self.__env("TELEGRAM_AUTH_ON", lambda: str(def_telegram_must_auth)).lower() == "true"
        self.whatsapp_must_auth = self.__env("WHATSAPP_AUTH_ON", lambda: str(def_whatsapp_must_auth)).lower() == "true"
        self.gumroad_must_auth = self.__env("GUMROAD_AUTH_ON", lambda: str(def_gumroad_must_auth)).lower() == "true"
        self.gumroad_seller_id_check = self.__env("GUMROAD_SELLER_ID_CHECK", lambda: str(def_gumroad_seller_id_check)).lower() == "true"
        self.gumroad_seller_id = self.__env("GUMROAD_SELLER_ID", lambda: def_gumroad_seller_id)
        self.whatsapp_phone_number_id = self.__env("WHATSAPP_PHONE_NUMBER_ID", lambda: def_whatsapp_phone_number_id)
        self.whatsapp_bot_phone_number = self.__env("WHATSAPP_BOT_PHONE_NUMBER", lambda: def_whatsapp_bot_phone_number)
        self.chat_history_depth = int(self.__env("CHAT_HISTORY_DEPTH", lambda: str(def_chat_history_depth)))
        self.chat_debounce_delay_s = float(self.__env("CHAT_DEBOUNCE_DELAY_S", lambda: str(def_chat_debounce_delay_s)))
        self.cleanup_message_retention_days = int(self.__env("CLEANUP_MESSAGE_RETENTION_DAYS", lambda: str(def_cleanup_message_retention_days)))
        self.cleanup_price_alert_staleness_days = int(self.__env("CLEANUP_PRICE_ALERT_STALENESS_DAYS", lambda: str(def_cleanup_price_alert_staleness_days)))
        self.cleanup_sponsorship_staleness_days = int(self.__env("CLEANUP_SPONSORSHIP_STALENESS_DAYS", lambda: str(def_cleanup_sponsorship_staleness_days)))
        self.github_issues_repo = self.__env("THE_AGENT_ISSUES_REPO", lambda: def_github_issues_repo)
        self.issue_templates_abs_path = self.__env("THE_AGENT_ISSUE_TEMPLATES_PATH", lambda: def_issue_templates_path)
        self.jwt_expires_in_minutes = int(self.__env("JWT_EXPIRES_IN_MINUTES", lambda: str(def_jwt_expires_in_minutes)))
        self.backoffice_url_base = self.__env("BACKOFFICE_URL_BASE", lambda: def_backoffice_url_base)
        self.public_api_base_url = self.__env("PUBLIC_API_BASE_URL", lambda: def_public_api_base_url).rstrip("/")
        self.main_language_name = self.__env("MAIN_LANGUAGE_NAME", lambda: def_main_language_name)
        self.main_language_iso_code = self.__env("MAIN_LANGUAGE_ISO_CODE", lambda: def_main_language_iso_code)
        self.uploadcare_public_key = self.__env("UPLOADCARE_PUBLIC_KEY", lambda: def_uploadcare_public_key)
        self.uploadcare_cdn_id = self.__env("UPLOADCARE_CDN_ID", lambda: def_uploadcare_cdn_id)
        self.url_shortener_base_url = self.__env("URL_SHORTENER_BASE_URL", lambda: def_url_shortener_base_url)
        self.version = self.__env("VERSION", lambda: def_version)
        self.usage_maintenance_fee_credits = float(self.__env("USAGE_MAINTENANCE_FEE_CREDITS", lambda: str(def_usage_maintenance_fee_credits)))
        self.products_config_path = self.__env("PRODUCTS_CONFIG_PATH", lambda: def_products_config_path)
        self.products = self.__load_products()
        self.logos_config_path = self.__env("LOGOS_CONFIG_PATH", lambda: def_logos_config_path)
        self.logos = self.__load_logos()
        self.fonts_dir = self.__env("FONTS_DIR", lambda: def_fonts_dir)
        self.s3_base_url = self.__env("S3_BASE_URL", lambda: def_s3_base_url)
        self.s3_region = self.__env("S3_REGION", lambda: def_s3_region)
        self.s3_bucket = self.__env("S3_BUCKET", lambda: def_s3_bucket)
        self.attachment_public_token_ttl_seconds = int(self.__env("ATTACHMENT_PUBLIC_TOKEN_TTL_SECONDS", lambda: str(def_attachment_public_token_ttl_seconds)))

        self.__set_up_db(def_db_user, def_db_pass, def_db_host, def_db_name)
        self.api_key = self.__senv("API_KEY", lambda: def_api_key)
        self.telegram_auth_key = self.__senv("TELEGRAM_API_UPDATE_AUTH_TOKEN", lambda: def_telegram_auth_key)
        self.telegram_bot_token = self.__senv("TELEGRAM_BOT_TOKEN", lambda: def_telegram_bot_token)
        self.whatsapp_auth_key = self.__senv("WHATSAPP_API_UPDATE_AUTH_TOKEN", lambda: def_whatsapp_auth_key)
        self.whatsapp_app_secret = self.__senv("WHATSAPP_APP_SECRET", lambda: def_whatsapp_app_secret)
        self.whatsapp_bot_token = self.__senv("WHATSAPP_BOT_TOKEN", lambda: def_whatsapp_bot_token)
        self.gumroad_auth_key = self.__senv("GUMROAD_PING_AUTH_TOKEN", lambda: def_gumroad_auth_key)
        self.jwt_secret_key = self.__senv("JWT_SECRET_KEY", lambda: def_jwt_secret_key)
        self.github_issues_token = self.__senv("THE_AGENT_ISSUES_TOKEN", lambda: def_github_issues_token)
        self.free_img_host_token = self.__senv("FREE_IMG_HOST_TOKEN", lambda: def_free_img_host_token)
        self.token_encrypt_secret = self.__senv("TOKEN_ENCRYPT_SECRET", lambda: def_token_encrypt_secret)
        self.uploadcare_private_key = self.__senv("UPLOADCARE_PRIVATE_KEY", lambda: def_uploadcare_private_key)
        self.url_shortener_api_key = self.__senv("URL_SHORTENER_API_KEY", lambda: def_url_shortener_api_key)
        self.platform_open_ai_key = self.__senv("PLATFORM_OPEN_AI_KEY", lambda: def_platform_open_ai_key)
        self.platform_anthropic_key = self.__senv("PLATFORM_ANTHROPIC_KEY", lambda: def_platform_anthropic_key)
        self.platform_google_ai_key = self.__senv("PLATFORM_GOOGLE_AI_KEY", lambda: def_platform_google_ai_key)
        self.platform_perplexity_key = self.__senv("PLATFORM_PERPLEXITY_KEY", lambda: def_platform_perplexity_key)
        self.platform_replicate_key = self.__senv("PLATFORM_REPLICATE_KEY", lambda: def_platform_replicate_key)
        self.platform_rapid_api_key = self.__senv("PLATFORM_RAPID_API_KEY", lambda: def_platform_rapid_api_key)
        self.platform_coinmarketcap_key = self.__senv("PLATFORM_COINMARKETCAP_KEY", lambda: def_platform_coinmarketcap_key)
        self.platform_x_key = self.__senv("PLATFORM_X_KEY", lambda: def_platform_x_key)
        self.platform_x_ai_key = self.__senv("PLATFORM_X_AI_KEY", lambda: def_platform_x_ai_key)
        self.s3_access_key = self.__senv("S3_ACCESS_KEY", lambda: def_s3_access_key)
        self.s3_secret_key = self.__senv("S3_SECRET_KEY", lambda: def_s3_secret_key)
        # @formatter:on

    def __set_up_db(self, def_db_user: SecretStr, def_db_pass: SecretStr, def_db_host: SecretStr, def_db_name: SecretStr):
        db_user = self.__senv("POSTGRES_USER", lambda: def_db_user).get_secret_value()
        db_pass = self.__senv("POSTGRES_PASS", lambda: def_db_pass).get_secret_value()
        db_host = self.__senv("POSTGRES_HOST", lambda: def_db_host).get_secret_value()
        db_name = self.__senv("POSTGRES_DB", lambda: def_db_name).get_secret_value()
        db_port = 5432  # standard for postgres
        self.db_url = SecretStr(f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")

    @staticmethod
    def __env(name: str, default: Callable[[], str]) -> str:
        env_value = os.environ.get(name, "").strip()
        return env_value if env_value else default()

    @staticmethod
    def __senv(name: str, default: Callable[[], SecretStr]) -> SecretStr:
        env_value = os.environ.get(name, "").strip()
        return SecretStr(env_value) if env_value else default()

    def __load_products(self) -> dict[str, ConfiguredProduct]:
        with open(self.products_config_path) as f:
            data: dict[str, any] = yaml.safe_load(f)
        try:
            return {
                p["id"]: ConfiguredProduct(id = p["id"], credits = p["credits"], name = p["name"], url = p["url"])
                for p in data["products"]
            }
        except Exception as e:
            logging.error(f"Failed to parse products config from '{self.products_config_path}': {e}")
            return {}

    def __load_logos(self) -> dict[str, str]:
        with open(self.logos_config_path) as f:
            data: dict[str, any] = yaml.safe_load(f)
        try:
            return {k: v for k, v in data["logos"].items()}
        except Exception as e:
            logging.error(f"Failed to parse logos config from '{self.logos_config_path}': {e}")
            return {}


config = Config()
