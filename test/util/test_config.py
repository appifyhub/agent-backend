import os
import unittest

from util.config import Config

PRODUCTS_FIXTURE_PATH = "test/fixtures/products.yaml"
LOGOS_FIXTURE_PATH = "test/fixtures/logos.yaml"


class ConfigTest(unittest.TestCase):

    # noinspection PyTypeHints
    original_env: dict

    def setUp(self):
        self.original_env = os.environ.copy()
        os.environ.clear()
        Config._instances = {}

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        Config._instances = {}

    def test_default_config(self):
        config = Config()

        self.assertEqual(config.log_level, "info")
        self.assertEqual(config.log_telegram_update, False)
        self.assertEqual(config.log_whatsapp_update, False)
        self.assertEqual(config.web_retries, 3)
        self.assertEqual(config.web_retry_delay_s, 1)
        self.assertEqual(config.web_timeout_s, 10)
        self.assertEqual(config.max_sponsorships_per_user, 2)
        self.assertEqual(config.max_users, 100)
        self.assertEqual(config.default_max_output_tokens, 3500)
        self.assertEqual(config.website_url, "https://agent.appifyhub.com")
        self.assertEqual(config.parent_organization, "AppifyHub")
        self.assertEqual(config.agent_bot_name, "The Agent")
        self.assertEqual(config.background_bot_name, "The Agent's Pulse")
        self.assertEqual(config.background_bot_username, "the_agent_pulse")
        self.assertEqual(config.github_bot_username, "the-agent")
        self.assertEqual(config.github_bot_id, 1234567890)
        self.assertEqual(config.telegram_bot_username, "the_agent")
        self.assertEqual(config.telegram_bot_id, 1234567890)
        self.assertEqual(config.telegram_api_base_url, "https://api.telegram.org")
        self.assertEqual(config.telegram_must_auth, False)
        self.assertEqual(config.whatsapp_must_auth, False)
        self.assertEqual(config.gumroad_must_auth, False)
        self.assertEqual(config.gumroad_seller_id_check, False)
        self.assertEqual(config.gumroad_seller_id, "invalid")
        self.assertEqual(config.whatsapp_phone_number_id, "invalid")
        self.assertEqual(config.whatsapp_bot_phone_number, "11234567890")
        self.assertEqual(config.chat_history_depth, 30)
        self.assertEqual(config.chat_debounce_delay_s, 1.0)
        self.assertEqual(config.cleanup_message_retention_days, 30)
        self.assertEqual(config.cleanup_price_alert_staleness_days, 360)
        self.assertEqual(config.cleanup_sponsorship_staleness_days, 30)
        self.assertEqual(config.github_issues_repo, "appifyhub/agent-backend")
        self.assertEqual(config.issue_templates_abs_path, ".github/ISSUE_TEMPLATE")
        self.assertEqual(config.jwt_expires_in_minutes, 30)
        self.assertEqual(config.backoffice_url_base, "http://localhost:5173")
        self.assertEqual(config.main_language_name, "English")
        self.assertEqual(config.main_language_iso_code, "en")
        self.assertEqual(config.uploadcare_public_key, "invalid")
        self.assertEqual(config.uploadcare_cdn_id, "invalid")
        self.assertEqual(config.url_shortener_base_url, "https://urls.appifyhub.com")
        self.assertEqual(config.version, "dev")
        self.assertEqual(config.usage_maintenance_fee_credits, 0.0)
        self.assertEqual(config.products_config_path, "config/products.yaml")
        self.assertEqual(config.logos_config_path, "config/logos.yaml")
        self.assertEqual(config.fonts_dir, "src/assets/fonts")

        self.assertEqual(config.db_url.get_secret_value(), "postgresql://root:root@localhost:5432/agent")
        self.assertTrue(config.api_key.get_secret_value())  # Check if API key is generated
        self.assertEqual(config.telegram_auth_key.get_secret_value(), "it_is_really_telegram")
        self.assertEqual(config.telegram_bot_token.get_secret_value(), "invalid")
        self.assertEqual(config.whatsapp_auth_key.get_secret_value(), "it_is_really_whatsapp")
        self.assertEqual(config.whatsapp_app_secret.get_secret_value(), "invalid")
        self.assertEqual(config.gumroad_auth_key.get_secret_value(), "it_is_really_gumroad")
        self.assertEqual(config.jwt_secret_key.get_secret_value(), "default")
        self.assertEqual(config.github_issues_token.get_secret_value(), "invalid")
        self.assertEqual(config.free_img_host_token.get_secret_value(), "invalid")
        self.assertEqual(config.token_encrypt_secret.get_secret_value(), "default")
        self.assertEqual(config.uploadcare_private_key.get_secret_value(), "invalid")
        self.assertEqual(config.url_shortener_api_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_open_ai_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_anthropic_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_google_ai_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_perplexity_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_replicate_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_rapid_api_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_coinmarketcap_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_x_key.get_secret_value(), "invalid")
        self.assertEqual(config.platform_x_ai_key.get_secret_value(), "invalid")

    def test_custom_config(self):
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["LOG_TG_UPDATE"] = "true"
        os.environ["LOG_WA_UPDATE"] = "true"
        os.environ["WEB_RETRIES"] = "5"
        os.environ["WEB_RETRY_DELAY_S"] = "2"
        os.environ["WEB_TIMEOUT_S"] = "20"
        os.environ["MAX_SPONSORSHIPS_PER_USER"] = "5"
        os.environ["MAX_USERS"] = "10"
        os.environ["DEFAULT_MAX_OUTPUT_TOKENS"] = "5000"
        os.environ["WEBSITE_URL"] = "https://new.agent.appifyhub.com"
        os.environ["PARENT_ORGANIZATION"] = "New"
        os.environ["AGENT_BOT_NAME"] = "The New Agent"
        os.environ["BACKGROUND_BOT_NAME"] = "The New Agent's Pulse"
        os.environ["BACKGROUND_BOT_USERNAME"] = "the_new_agent_pulse"
        os.environ["GITHUB_BOT_USERNAME"] = "the-new-agent"
        os.environ["GITHUB_BOT_ID"] = "1234"
        os.environ["TELEGRAM_BOT_USERNAME"] = "the_new_agent"
        os.environ["TELEGRAM_BOT_ID"] = "1234"
        os.environ["TELEGRAM_API_BASE_URL"] = "https://new.api.telegram.org"
        os.environ["TELEGRAM_AUTH_ON"] = "True"
        os.environ["WHATSAPP_AUTH_ON"] = "True"
        os.environ["GUMROAD_AUTH_ON"] = "True"
        os.environ["GUMROAD_SELLER_ID_CHECK"] = "True"
        os.environ["GUMROAD_SELLER_ID"] = "test-seller-123"
        os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "9876543210"
        os.environ["WHATSAPP_BOT_PHONE_NUMBER"] = "19876543210"
        os.environ["CHAT_HISTORY_DEPTH"] = "10"
        os.environ["CHAT_DEBOUNCE_DELAY_S"] = "2.5"
        os.environ["CLEANUP_MESSAGE_RETENTION_DAYS"] = "60"
        os.environ["CLEANUP_PRICE_ALERT_STALENESS_DAYS"] = "180"
        os.environ["CLEANUP_SPONSORSHIP_STALENESS_DAYS"] = "14"
        os.environ["THE_AGENT_ISSUES_REPO"] = "appifyhub/the-new-agent"
        os.environ["THE_AGENT_ISSUE_TEMPLATES_PATH"] = "issue_templates"
        os.environ["JWT_EXPIRES_IN_MINUTES"] = "10"
        os.environ["BACKOFFICE_URL_BASE"] = "https://example.com"
        os.environ["MAIN_LANGUAGE_NAME"] = "German"
        os.environ["MAIN_LANGUAGE_ISO_CODE"] = "de"
        os.environ["UPLOADCARE_PUBLIC_KEY"] = "public-key-123"
        os.environ["UPLOADCARE_CDN_ID"] = "cdn-id-123"
        os.environ["URL_SHORTENER_BASE_URL"] = "https://custom.to.appifyhub.com"
        os.environ["VERSION"] = "custom"
        os.environ["USAGE_MAINTENANCE_FEE_CREDITS"] = "0.5"
        os.environ["FONTS_DIR"] = "/custom/path/fonts"

        os.environ["POSTGRES_USER"] = "admin"
        os.environ["POSTGRES_PASS"] = "admin123"
        os.environ["POSTGRES_HOST"] = "db.example.com"
        os.environ["POSTGRES_DB"] = "test_db"
        os.environ["API_KEY"] = "1111-2222-3333-4444"
        os.environ["TELEGRAM_API_UPDATE_AUTH_TOKEN"] = "abcd1234"
        os.environ["TELEGRAM_BOT_TOKEN"] = "id:sha"
        os.environ["WHATSAPP_API_UPDATE_AUTH_TOKEN"] = "efgh5678"
        os.environ["WHATSAPP_APP_SECRET"] = "ijkl9012"
        os.environ["WHATSAPP_BOT_TOKEN"] = "bot_token_123"
        os.environ["GUMROAD_PING_AUTH_TOKEN"] = "mnop3456"
        os.environ["JWT_SECRET_KEY"] = "custom"
        os.environ["THE_AGENT_ISSUES_TOKEN"] = "sk-gi-valid"
        os.environ["FREE_IMG_HOST_TOKEN"] = "sk-im-valid"
        os.environ["TOKEN_ENCRYPT_SECRET"] = "custom-encryption-key"
        os.environ["UPLOADCARE_PRIVATE_KEY"] = "private-key-123"
        os.environ["URL_SHORTENER_API_KEY"] = "url-shortener-key-123"
        os.environ["PLATFORM_OPEN_AI_KEY"] = "platform-openai-key"
        os.environ["PLATFORM_ANTHROPIC_KEY"] = "platform-anthropic-key"
        os.environ["PLATFORM_GOOGLE_AI_KEY"] = "platform-google-key"
        os.environ["PLATFORM_PERPLEXITY_KEY"] = "platform-perplexity-key"
        os.environ["PLATFORM_REPLICATE_KEY"] = "platform-replicate-key"
        os.environ["PLATFORM_RAPID_API_KEY"] = "platform-rapid-api-key"
        os.environ["PLATFORM_COINMARKETCAP_KEY"] = "platform-coinmarketcap-key"
        os.environ["PLATFORM_X_KEY"] = "platform-x-key"
        os.environ["PLATFORM_X_AI_KEY"] = "platform-x-ai-key"

        config = Config()

        self.assertEqual(config.log_level, "debug")
        self.assertEqual(config.log_telegram_update, True)
        self.assertEqual(config.log_whatsapp_update, True)
        self.assertEqual(config.web_retries, 5)
        self.assertEqual(config.web_retry_delay_s, 2)
        self.assertEqual(config.web_timeout_s, 20)
        self.assertEqual(config.max_sponsorships_per_user, 5)
        self.assertEqual(config.max_users, 10)
        self.assertEqual(config.default_max_output_tokens, 5000)
        self.assertEqual(config.website_url, "https://new.agent.appifyhub.com")
        self.assertEqual(config.parent_organization, "New")
        self.assertEqual(config.agent_bot_name, "The New Agent")
        self.assertEqual(config.background_bot_name, "The New Agent's Pulse")
        self.assertEqual(config.background_bot_username, "the_new_agent_pulse")
        self.assertEqual(config.github_bot_username, "the-new-agent")
        self.assertEqual(config.github_bot_id, 1234)
        self.assertEqual(config.telegram_bot_username, "the_new_agent")
        self.assertEqual(config.telegram_bot_id, 1234)
        self.assertEqual(config.telegram_api_base_url, "https://new.api.telegram.org")
        self.assertEqual(config.telegram_must_auth, True)
        self.assertEqual(config.whatsapp_must_auth, True)
        self.assertEqual(config.gumroad_must_auth, True)
        self.assertEqual(config.gumroad_seller_id_check, True)
        self.assertEqual(config.gumroad_seller_id, "test-seller-123")
        self.assertEqual(config.whatsapp_phone_number_id, "9876543210")
        self.assertEqual(config.whatsapp_bot_phone_number, "19876543210")
        self.assertEqual(config.chat_history_depth, 10)
        self.assertEqual(config.chat_debounce_delay_s, 2.5)
        self.assertEqual(config.cleanup_message_retention_days, 60)
        self.assertEqual(config.cleanup_price_alert_staleness_days, 180)
        self.assertEqual(config.cleanup_sponsorship_staleness_days, 14)
        self.assertEqual(config.github_issues_repo, "appifyhub/the-new-agent")
        self.assertEqual(config.issue_templates_abs_path, "issue_templates")
        self.assertEqual(config.jwt_expires_in_minutes, 10)
        self.assertEqual(config.backoffice_url_base, "https://example.com")
        self.assertEqual(config.main_language_name, "German")
        self.assertEqual(config.main_language_iso_code, "de")
        self.assertEqual(config.uploadcare_public_key, "public-key-123")
        self.assertEqual(config.uploadcare_cdn_id, "cdn-id-123")
        self.assertEqual(config.url_shortener_base_url, "https://custom.to.appifyhub.com")
        self.assertEqual(config.version, "custom")
        self.assertEqual(config.usage_maintenance_fee_credits, 0.5)
        self.assertEqual(config.fonts_dir, "/custom/path/fonts")

        self.assertEqual(config.db_url.get_secret_value(), "postgresql://admin:admin123@db.example.com:5432/test_db")
        self.assertEqual(config.api_key.get_secret_value(), "1111-2222-3333-4444")
        self.assertEqual(config.telegram_auth_key.get_secret_value(), "abcd1234")
        self.assertEqual(config.telegram_bot_token.get_secret_value(), "id:sha")
        self.assertEqual(config.whatsapp_auth_key.get_secret_value(), "efgh5678")
        self.assertEqual(config.whatsapp_app_secret.get_secret_value(), "ijkl9012")
        self.assertEqual(config.whatsapp_bot_token.get_secret_value(), "bot_token_123")
        self.assertEqual(config.gumroad_auth_key.get_secret_value(), "mnop3456")
        self.assertEqual(config.jwt_secret_key.get_secret_value(), "custom")
        self.assertEqual(config.github_issues_token.get_secret_value(), "sk-gi-valid")
        self.assertEqual(config.free_img_host_token.get_secret_value(), "sk-im-valid")
        self.assertEqual(config.token_encrypt_secret.get_secret_value(), "custom-encryption-key")
        self.assertEqual(config.uploadcare_private_key.get_secret_value(), "private-key-123")
        self.assertEqual(config.url_shortener_api_key.get_secret_value(), "url-shortener-key-123")
        self.assertEqual(config.platform_open_ai_key.get_secret_value(), "platform-openai-key")
        self.assertEqual(config.platform_anthropic_key.get_secret_value(), "platform-anthropic-key")
        self.assertEqual(config.platform_google_ai_key.get_secret_value(), "platform-google-key")
        self.assertEqual(config.platform_perplexity_key.get_secret_value(), "platform-perplexity-key")
        self.assertEqual(config.platform_replicate_key.get_secret_value(), "platform-replicate-key")
        self.assertEqual(config.platform_rapid_api_key.get_secret_value(), "platform-rapid-api-key")
        self.assertEqual(config.platform_coinmarketcap_key.get_secret_value(), "platform-coinmarketcap-key")
        self.assertEqual(config.platform_x_key.get_secret_value(), "platform-x-key")
        self.assertEqual(config.platform_x_ai_key.get_secret_value(), "platform-x-ai-key")

    def test_products_loaded_from_yaml(self):
        config = Config(def_products_config_path = PRODUCTS_FIXTURE_PATH)
        products = config.products

        self.assertEqual(len(products), 2)
        self.assertEqual(products["PROD_100"].credits, 100)
        self.assertEqual(products["PROD_100"].name, "Pack of 100")
        self.assertEqual(products["PROD_100"].url, "https://store.appifyhub.com/l/abot-credits-100")
        self.assertEqual(products["PROD_DONATION"].credits, 0)
        self.assertEqual(products["PROD_DONATION"].name, "Green Tea")
        self.assertEqual(products["PROD_DONATION"].url, "https://store.appifyhub.com/coffee")

    def test_products_loaded_once_at_init(self):
        config = Config(def_products_config_path = PRODUCTS_FIXTURE_PATH)

        first = config.products
        second = config.products

        self.assertIs(first, second)

    def test_logos_loaded_from_yaml(self):
        config = Config(def_logos_config_path = LOGOS_FIXTURE_PATH)
        logos = config.logos

        self.assertEqual(len(logos), 5)
        self.assertEqual(logos["agent_logo_color"], "https://example.com/logo-color.svg")
        self.assertEqual(logos["agent_logo_light"], "https://example.com/logo-light.svg")
        self.assertEqual(logos["agent_logo_dark"], "https://example.com/logo-dark.svg")
        self.assertEqual(logos["x_logo_light"], "https://example.com/x-light.svg")
        self.assertEqual(logos["x_logo_dark"], "https://example.com/x-dark.svg")

    def test_logos_loaded_once_at_init(self):
        config = Config(def_logos_config_path = LOGOS_FIXTURE_PATH)

        first = config.logos
        second = config.logos

        self.assertIs(first, second)
