import unittest
from dataclasses import replace
from datetime import date
from uuid import UUID

from pydantic import SecretStr

from db.model.user import UserDB
from features.users.user import User
from features.users.user_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data
from features.users.user_remote_data import UserRemoteData


class UserMapperTest(unittest.TestCase):

    user_id: UUID
    created_at: date

    def setUp(self):
        self.user_id = UUID("11111111-1111-1111-1111-111111111111")
        self.created_at = date(2026, 1, 1)

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields_and_wraps_secrets(self):
        db_model = self.__db_model()

        result = domain(db_model)

        self.assertEqual(result.id, self.user_id)
        self.assertEqual(result.created_at, self.created_at)
        self.assertEqual(result.full_name, "Test User")
        self.assertEqual(result.about_me.get_secret_value(), "about")
        self.assertEqual(result.custom_prompt.get_secret_value(), "prompt")
        self.assertEqual(result.telegram_username, "telegram-user")
        self.assertEqual(result.telegram_chat_id, "tg-chat")
        self.assertEqual(result.telegram_user_id, 123)
        self.assertEqual(result.whatsapp_user_id, "wa-user")
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "15550001111")
        self.assertEqual(result.open_ai_key.get_secret_value(), "open-ai")
        self.assertEqual(result.anthropic_key.get_secret_value(), "anthropic")
        self.assertEqual(result.google_ai_key.get_secret_value(), "google")
        self.assertEqual(result.perplexity_key.get_secret_value(), "perplexity")
        self.assertEqual(result.replicate_key.get_secret_value(), "replicate")
        self.assertEqual(result.rapid_api_key.get_secret_value(), "rapid")
        self.assertEqual(result.coinmarketcap_key.get_secret_value(), "coinmarketcap")
        self.assertEqual(result.twelve_data_api_key.get_secret_value(), "twelve-data")
        self.assertEqual(result.x_key.get_secret_value(), "x")
        self.assertEqual(result.x_ai_key.get_secret_value(), "x-ai")
        self.assertEqual(result.tool_choice_chat, "chat-tool")
        self.assertEqual(result.tool_choice_reasoning, "reasoning-tool")
        self.assertEqual(result.tool_choice_copywriting, "copywriting-tool")
        self.assertEqual(result.tool_choice_vision, "vision-tool")
        self.assertEqual(result.tool_choice_hearing, "hearing-tool")
        self.assertEqual(result.tool_choice_images_gen, "images-gen-tool")
        self.assertEqual(result.tool_choice_videos_gen, "videos-gen-tool")
        self.assertEqual(result.tool_choice_images_edit, "images-edit-tool")
        self.assertEqual(result.tool_choice_search, "search-tool")
        self.assertEqual(result.tool_choice_embedding, "embedding-tool")
        self.assertEqual(result.tool_choice_api_fiat_exchange, "fiat-tool")
        self.assertEqual(result.tool_choice_api_crypto_exchange, "crypto-tool")
        self.assertEqual(result.tool_choice_api_stock_quote, "stock-tool")
        self.assertEqual(result.tool_choice_api_twitter, "twitter-tool")
        self.assertEqual(result.credit_balance, 123.45)
        self.assertTrue(result.is_on_waitlist)
        self.assertTrue(result.is_invited_to_start)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.connect_key, "CONN-KEY-0001")
        self.assertEqual(result.group, UserDB.Group.developer)

    def test_db_maps_all_fields_and_unwraps_secrets(self):
        domain_model = self.__domain_model()

        result = db(domain_model)

        self.assertEqual(result.id, self.user_id)
        self.assertEqual(result.created_at, self.created_at)
        self.assertEqual(result.full_name, "Test User")
        self.assertEqual(result.about_me, "about")
        self.assertEqual(result.custom_prompt, "prompt")
        self.assertEqual(result.telegram_username, "telegram-user")
        self.assertEqual(result.telegram_chat_id, "tg-chat")
        self.assertEqual(result.telegram_user_id, 123)
        self.assertEqual(result.whatsapp_user_id, "wa-user")
        self.assertEqual(result.whatsapp_phone_number, "15550001111")
        self.assertEqual(result.open_ai_key, "open-ai")
        self.assertEqual(result.anthropic_key, "anthropic")
        self.assertEqual(result.google_ai_key, "google")
        self.assertEqual(result.perplexity_key, "perplexity")
        self.assertEqual(result.replicate_key, "replicate")
        self.assertEqual(result.rapid_api_key, "rapid")
        self.assertEqual(result.coinmarketcap_key, "coinmarketcap")
        self.assertEqual(result.twelve_data_api_key, "twelve-data")
        self.assertEqual(result.x_key, "x")
        self.assertEqual(result.x_ai_key, "x-ai")
        self.assertEqual(result.tool_choice_videos_gen, "videos-gen-tool")
        self.assertEqual(result.tool_choice_api_stock_quote, "stock-tool")
        self.assertEqual(result.tool_choice_api_twitter, "twitter-tool")
        self.assertEqual(result.credit_balance, 123.45)
        self.assertTrue(result.is_on_waitlist)
        self.assertTrue(result.is_invited_to_start)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.connect_key, "CONN-KEY-0001")
        self.assertEqual(result.group, UserDB.Group.developer)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = self.__db_model()
        replacement = User(
            id = UUID("22222222-2222-2222-2222-222222222222"),
            created_at = date(2026, 2, 2),
            full_name = "Updated User",
            telegram_username = "updated-telegram",
            telegram_chat_id = "updated-chat",
            telegram_user_id = 456,
            whatsapp_user_id = "updated-wa",
            whatsapp_phone_number = SecretStr("16660002222"),
            open_ai_key = SecretStr("updated-open-ai"),
            credit_balance = 999.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = False,
            connect_key = "UPDATED-KEY",
            group = UserDB.Group.standard,
        )

        apply_to_db_model(replacement, db_model)

        self.assertEqual(db_model.id, self.user_id)
        self.assertEqual(db_model.created_at, self.created_at)
        self.assertEqual(db_model.full_name, "Updated User")
        self.assertIsNone(db_model.about_me)
        self.assertIsNone(db_model.custom_prompt)
        self.assertEqual(db_model.telegram_username, "updated-telegram")
        self.assertEqual(db_model.telegram_chat_id, "updated-chat")
        self.assertEqual(db_model.telegram_user_id, 456)
        self.assertEqual(db_model.whatsapp_user_id, "updated-wa")
        self.assertEqual(db_model.whatsapp_phone_number, "16660002222")
        self.assertEqual(db_model.open_ai_key, "updated-open-ai")
        self.assertIsNone(db_model.anthropic_key)
        self.assertIsNone(db_model.tool_choice_chat)
        self.assertEqual(db_model.credit_balance, 999.0)
        self.assertFalse(db_model.is_on_waitlist)
        self.assertFalse(db_model.is_invited_to_start)
        self.assertFalse(db_model.are_policies_accepted)
        self.assertEqual(db_model.connect_key, "UPDATED-KEY")
        self.assertEqual(db_model.group, UserDB.Group.standard)

    def test_from_remote_data_uses_remote_fields_and_domain_defaults(self):
        remote_data = UserRemoteData(
            full_name = "Remote User",
            telegram_username = "remote-telegram",
            telegram_chat_id = "remote-chat",
            telegram_user_id = 987,
            whatsapp_user_id = "remote-wa",
            whatsapp_phone_number = SecretStr("17770003333"),
        )

        result = from_remote_data(remote_data)

        self.assertIsNone(result.id)
        self.assertIsNone(result.created_at)
        self.assertEqual(result.full_name, "Remote User")
        self.assertEqual(result.telegram_username, "remote-telegram")
        self.assertEqual(result.telegram_chat_id, "remote-chat")
        self.assertEqual(result.telegram_user_id, 987)
        self.assertEqual(result.whatsapp_user_id, "remote-wa")
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "17770003333")
        self.assertFalse(result.is_on_waitlist)
        self.assertFalse(result.is_invited_to_start)
        self.assertFalse(result.are_policies_accepted)
        self.assertIsNotNone(result.connect_key)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_apply_remote_data_preserves_db_owned_fields_and_existing_full_name(self):
        existing = self.__domain_model()
        remote_data = UserRemoteData(
            full_name = "Remote Name",
            telegram_username = "remote-telegram",
            telegram_chat_id = "remote-chat",
            telegram_user_id = 777,
            whatsapp_user_id = None,
            whatsapp_phone_number = SecretStr("18880004444"),
        )

        result = apply_remote_data(existing, remote_data)

        self.assertEqual(result.id, existing.id)
        self.assertEqual(result.created_at, existing.created_at)
        self.assertEqual(result.full_name, existing.full_name)
        self.assertEqual(result.about_me, existing.about_me)
        self.assertEqual(result.custom_prompt, existing.custom_prompt)
        self.assertEqual(result.telegram_username, "remote-telegram")
        self.assertEqual(result.telegram_chat_id, existing.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, 777)
        self.assertEqual(result.whatsapp_user_id, existing.whatsapp_user_id)
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "18880004444")
        self.assertEqual(result.open_ai_key, existing.open_ai_key)
        self.assertEqual(result.credit_balance, existing.credit_balance)
        self.assertEqual(result.is_on_waitlist, existing.is_on_waitlist)
        self.assertEqual(result.connect_key, existing.connect_key)
        self.assertEqual(result.group, existing.group)

    def test_apply_remote_data_fills_missing_telegram_chat_id(self):
        existing = replace(self.__domain_model(), telegram_chat_id = None)
        remote_data = UserRemoteData(telegram_chat_id = "remote-chat")

        result = apply_remote_data(existing, remote_data)

        self.assertEqual(result.telegram_chat_id, "remote-chat")

    def test_apply_remote_data_fills_missing_full_name(self):
        existing = User(
            id = self.user_id,
            created_at = self.created_at,
            full_name = None,
            connect_key = "CONN-KEY-0001",
        )
        remote_data = UserRemoteData(full_name = "Remote Name")

        result = apply_remote_data(existing, remote_data)

        self.assertEqual(result.full_name, "Remote Name")

    def __domain_model(self) -> User:
        return User(
            id = self.user_id,
            created_at = self.created_at,
            full_name = "Test User",
            about_me = SecretStr("about"),
            custom_prompt = SecretStr("prompt"),
            telegram_username = "telegram-user",
            telegram_chat_id = "tg-chat",
            telegram_user_id = 123,
            whatsapp_user_id = "wa-user",
            whatsapp_phone_number = SecretStr("15550001111"),
            open_ai_key = SecretStr("open-ai"),
            anthropic_key = SecretStr("anthropic"),
            google_ai_key = SecretStr("google"),
            perplexity_key = SecretStr("perplexity"),
            replicate_key = SecretStr("replicate"),
            rapid_api_key = SecretStr("rapid"),
            coinmarketcap_key = SecretStr("coinmarketcap"),
            twelve_data_api_key = SecretStr("twelve-data"),
            x_key = SecretStr("x"),
            x_ai_key = SecretStr("x-ai"),
            tool_choice_chat = "chat-tool",
            tool_choice_reasoning = "reasoning-tool",
            tool_choice_copywriting = "copywriting-tool",
            tool_choice_vision = "vision-tool",
            tool_choice_hearing = "hearing-tool",
            tool_choice_images_gen = "images-gen-tool",
            tool_choice_videos_gen = "videos-gen-tool",
            tool_choice_images_edit = "images-edit-tool",
            tool_choice_search = "search-tool",
            tool_choice_embedding = "embedding-tool",
            tool_choice_api_fiat_exchange = "fiat-tool",
            tool_choice_api_crypto_exchange = "crypto-tool",
            tool_choice_api_stock_quote = "stock-tool",
            tool_choice_api_twitter = "twitter-tool",
            credit_balance = 123.45,
            is_on_waitlist = True,
            is_invited_to_start = True,
            are_policies_accepted = True,
            connect_key = "CONN-KEY-0001",
            group = UserDB.Group.developer,
        )

    def __db_model(self) -> UserDB:
        return UserDB(
            id = self.user_id,
            created_at = self.created_at,
            full_name = "Test User",
            about_me = "about",
            custom_prompt = "prompt",
            telegram_username = "telegram-user",
            telegram_chat_id = "tg-chat",
            telegram_user_id = 123,
            whatsapp_user_id = "wa-user",
            whatsapp_phone_number = "15550001111",
            open_ai_key = "open-ai",
            anthropic_key = "anthropic",
            google_ai_key = "google",
            perplexity_key = "perplexity",
            replicate_key = "replicate",
            rapid_api_key = "rapid",
            coinmarketcap_key = "coinmarketcap",
            twelve_data_api_key = "twelve-data",
            x_key = "x",
            x_ai_key = "x-ai",
            tool_choice_chat = "chat-tool",
            tool_choice_reasoning = "reasoning-tool",
            tool_choice_copywriting = "copywriting-tool",
            tool_choice_vision = "vision-tool",
            tool_choice_hearing = "hearing-tool",
            tool_choice_images_gen = "images-gen-tool",
            tool_choice_videos_gen = "videos-gen-tool",
            tool_choice_images_edit = "images-edit-tool",
            tool_choice_search = "search-tool",
            tool_choice_embedding = "embedding-tool",
            tool_choice_api_fiat_exchange = "fiat-tool",
            tool_choice_api_crypto_exchange = "crypto-tool",
            tool_choice_api_stock_quote = "stock-tool",
            tool_choice_api_twitter = "twitter-tool",
            credit_balance = 123.45,
            is_on_waitlist = True,
            is_invited_to_start = True,
            are_policies_accepted = True,
            connect_key = "CONN-KEY-0001",
            group = UserDB.Group.developer,
        )
