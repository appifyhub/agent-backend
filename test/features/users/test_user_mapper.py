import unittest
from dataclasses import replace
from datetime import date
from uuid import UUID

import stubs
from pydantic import SecretStr

from db.model.user import UserDB
from features.users.user_mapper import apply_remote_data, apply_to_db_model, db, domain, from_remote_data


class UserMapperTest(unittest.TestCase):

    def test_domain_returns_none_for_none_input(self):
        self.assertIsNone(domain(None))

    def test_db_returns_none_for_none_input(self):
        self.assertIsNone(db(None))

    def test_domain_maps_all_fields_and_wraps_secrets(self):
        db_model = stubs.db.user_db(
            full_name = "Mapper DB User",
            about_me = "db about",
            custom_prompt = "db prompt",
            telegram_username = "db-telegram",
            telegram_chat_id = "db-chat",
            whatsapp_user_id = "db-whatsapp",
            whatsapp_phone_number = "+15550000001",
            open_ai_key = "db-open-ai",
            anthropic_key = "db-anthropic",
            google_ai_key = "db-google",
            perplexity_key = "db-perplexity",
            replicate_key = "db-replicate",
            rapid_api_key = "db-rapid",
            coinmarketcap_key = "db-coinmarketcap",
            twelve_data_api_key = "db-twelve-data",
            x_key = "db-x",
            x_ai_key = "db-x-ai",
            tool_choice_chat = "db-chat-tool",
            tool_choice_reasoning = "db-reasoning-tool",
            tool_choice_copywriting = "db-copywriting-tool",
            tool_choice_vision = "db-vision-tool",
            tool_choice_hearing = "db-hearing-tool",
            tool_choice_images_gen = "db-images-tool",
            tool_choice_videos_gen = "db-videos-tool",
            tool_choice_search = "db-search-tool",
            tool_choice_embedding = "db-embedding-tool",
            tool_choice_api_fiat_exchange = "db-fiat-tool",
            tool_choice_api_crypto_exchange = "db-crypto-tool",
            tool_choice_api_stock_quote = "db-stock-tool",
            tool_choice_api_twitter = "db-twitter-tool",
            connect_key = "DB-CONNECT-KEY",
        )

        result = domain(db_model)

        self.assertEqual(result.id, db_model.id)
        self.assertEqual(result.created_at, db_model.created_at)
        self.assertEqual(result.full_name, db_model.full_name)
        self.assertEqual(result.about_me.get_secret_value(), db_model.about_me)
        self.assertEqual(result.custom_prompt.get_secret_value(), db_model.custom_prompt)
        self.assertEqual(result.telegram_username, db_model.telegram_username)
        self.assertEqual(result.telegram_chat_id, db_model.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, db_model.telegram_user_id)
        self.assertEqual(result.whatsapp_user_id, db_model.whatsapp_user_id)
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), db_model.whatsapp_phone_number)
        self.assertEqual(result.open_ai_key.get_secret_value(), db_model.open_ai_key)
        self.assertEqual(result.anthropic_key.get_secret_value(), db_model.anthropic_key)
        self.assertEqual(result.google_ai_key.get_secret_value(), db_model.google_ai_key)
        self.assertEqual(result.perplexity_key.get_secret_value(), db_model.perplexity_key)
        self.assertEqual(result.replicate_key.get_secret_value(), db_model.replicate_key)
        self.assertEqual(result.rapid_api_key.get_secret_value(), db_model.rapid_api_key)
        self.assertEqual(result.coinmarketcap_key.get_secret_value(), db_model.coinmarketcap_key)
        self.assertEqual(result.twelve_data_api_key.get_secret_value(), db_model.twelve_data_api_key)
        self.assertEqual(result.x_key.get_secret_value(), db_model.x_key)
        self.assertEqual(result.x_ai_key.get_secret_value(), db_model.x_ai_key)
        self.assertEqual(result.tool_choice_chat, db_model.tool_choice_chat)
        self.assertEqual(result.tool_choice_reasoning, db_model.tool_choice_reasoning)
        self.assertEqual(result.tool_choice_copywriting, db_model.tool_choice_copywriting)
        self.assertEqual(result.tool_choice_vision, db_model.tool_choice_vision)
        self.assertEqual(result.tool_choice_hearing, db_model.tool_choice_hearing)
        self.assertEqual(result.tool_choice_images_gen, db_model.tool_choice_images_gen)
        self.assertEqual(result.tool_choice_videos_gen, db_model.tool_choice_videos_gen)
        self.assertEqual(result.tool_choice_search, db_model.tool_choice_search)
        self.assertEqual(result.tool_choice_embedding, db_model.tool_choice_embedding)
        self.assertEqual(result.tool_choice_api_fiat_exchange, db_model.tool_choice_api_fiat_exchange)
        self.assertEqual(result.tool_choice_api_crypto_exchange, db_model.tool_choice_api_crypto_exchange)
        self.assertEqual(result.tool_choice_api_stock_quote, db_model.tool_choice_api_stock_quote)
        self.assertEqual(result.tool_choice_api_twitter, db_model.tool_choice_api_twitter)
        self.assertEqual(result.credit_balance, db_model.credit_balance)
        self.assertEqual(result.is_on_waitlist, db_model.is_on_waitlist)
        self.assertEqual(result.is_invited_to_start, db_model.is_invited_to_start)
        self.assertEqual(result.are_policies_accepted, db_model.are_policies_accepted)
        self.assertEqual(result.connect_key, db_model.connect_key)
        self.assertEqual(result.group, db_model.group)

    def test_db_maps_all_fields_and_unwraps_secrets(self):
        domain_model = stubs.domain.user(
            full_name = "Mapper Domain User",
            about_me = SecretStr("domain about"),
            custom_prompt = SecretStr("domain prompt"),
            telegram_username = "domain-telegram",
            telegram_chat_id = "domain-chat",
            whatsapp_user_id = "domain-whatsapp",
            whatsapp_phone_number = SecretStr("+15550000002"),
            open_ai_key = SecretStr("domain-open-ai"),
            anthropic_key = SecretStr("domain-anthropic"),
            google_ai_key = SecretStr("domain-google"),
            perplexity_key = SecretStr("domain-perplexity"),
            replicate_key = SecretStr("domain-replicate"),
            rapid_api_key = SecretStr("domain-rapid"),
            coinmarketcap_key = SecretStr("domain-coinmarketcap"),
            twelve_data_api_key = SecretStr("domain-twelve-data"),
            x_key = SecretStr("domain-x"),
            x_ai_key = SecretStr("domain-x-ai"),
            tool_choice_chat = "domain-chat-tool",
            tool_choice_reasoning = "domain-reasoning-tool",
            tool_choice_copywriting = "domain-copywriting-tool",
            tool_choice_vision = "domain-vision-tool",
            tool_choice_hearing = "domain-hearing-tool",
            tool_choice_images_gen = "domain-images-tool",
            tool_choice_videos_gen = "domain-videos-tool",
            tool_choice_search = "domain-search-tool",
            tool_choice_embedding = "domain-embedding-tool",
            tool_choice_api_fiat_exchange = "domain-fiat-tool",
            tool_choice_api_crypto_exchange = "domain-crypto-tool",
            tool_choice_api_stock_quote = "domain-stock-tool",
            tool_choice_api_twitter = "domain-twitter-tool",
            connect_key = "DOMAIN-CONNECT-KEY",
        )

        result = db(domain_model)

        self.assertEqual(result.id, domain_model.id)
        self.assertEqual(result.created_at, domain_model.created_at)
        self.assertEqual(result.full_name, domain_model.full_name)
        self.assertEqual(result.about_me, domain_model.about_me.get_secret_value())
        self.assertEqual(result.custom_prompt, domain_model.custom_prompt.get_secret_value())
        self.assertEqual(result.telegram_username, domain_model.telegram_username)
        self.assertEqual(result.telegram_chat_id, domain_model.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, domain_model.telegram_user_id)
        self.assertEqual(result.whatsapp_user_id, domain_model.whatsapp_user_id)
        self.assertEqual(result.whatsapp_phone_number, domain_model.whatsapp_phone_number.get_secret_value())
        self.assertEqual(result.open_ai_key, domain_model.open_ai_key.get_secret_value())
        self.assertEqual(result.anthropic_key, domain_model.anthropic_key.get_secret_value())
        self.assertEqual(result.google_ai_key, domain_model.google_ai_key.get_secret_value())
        self.assertEqual(result.perplexity_key, domain_model.perplexity_key.get_secret_value())
        self.assertEqual(result.replicate_key, domain_model.replicate_key.get_secret_value())
        self.assertEqual(result.rapid_api_key, domain_model.rapid_api_key.get_secret_value())
        self.assertEqual(result.coinmarketcap_key, domain_model.coinmarketcap_key.get_secret_value())
        self.assertEqual(result.twelve_data_api_key, domain_model.twelve_data_api_key.get_secret_value())
        self.assertEqual(result.x_key, domain_model.x_key.get_secret_value())
        self.assertEqual(result.x_ai_key, domain_model.x_ai_key.get_secret_value())
        self.assertEqual(result.tool_choice_chat, domain_model.tool_choice_chat)
        self.assertEqual(result.tool_choice_reasoning, domain_model.tool_choice_reasoning)
        self.assertEqual(result.tool_choice_copywriting, domain_model.tool_choice_copywriting)
        self.assertEqual(result.tool_choice_vision, domain_model.tool_choice_vision)
        self.assertEqual(result.tool_choice_hearing, domain_model.tool_choice_hearing)
        self.assertEqual(result.tool_choice_images_gen, domain_model.tool_choice_images_gen)
        self.assertEqual(result.tool_choice_videos_gen, domain_model.tool_choice_videos_gen)
        self.assertEqual(result.tool_choice_search, domain_model.tool_choice_search)
        self.assertEqual(result.tool_choice_embedding, domain_model.tool_choice_embedding)
        self.assertEqual(result.tool_choice_api_fiat_exchange, domain_model.tool_choice_api_fiat_exchange)
        self.assertEqual(result.tool_choice_api_crypto_exchange, domain_model.tool_choice_api_crypto_exchange)
        self.assertEqual(result.tool_choice_api_stock_quote, domain_model.tool_choice_api_stock_quote)
        self.assertEqual(result.tool_choice_api_twitter, domain_model.tool_choice_api_twitter)
        self.assertEqual(result.credit_balance, domain_model.credit_balance)
        self.assertEqual(result.is_on_waitlist, domain_model.is_on_waitlist)
        self.assertEqual(result.is_invited_to_start, domain_model.is_invited_to_start)
        self.assertEqual(result.are_policies_accepted, domain_model.are_policies_accepted)
        self.assertEqual(result.connect_key, domain_model.connect_key)
        self.assertEqual(result.group, domain_model.group)

    def test_apply_to_db_model_updates_mutable_fields_and_preserves_identity(self):
        db_model = stubs.db.user_db()
        original_id = db_model.id
        original_created_at = db_model.created_at
        replacement = stubs.domain.user(
            id = UUID("22222222-2222-2222-2222-222222222222"),
            created_at = date(2026, 2, 2),
            full_name = "Updated User",
            about_me = None,
            custom_prompt = None,
            telegram_username = "updated-telegram",
            telegram_chat_id = "updated-chat",
            telegram_user_id = 456,
            whatsapp_user_id = "updated-wa",
            whatsapp_phone_number = SecretStr("16660002222"),
            open_ai_key = SecretStr("updated-open-ai"),
            anthropic_key = None,
            tool_choice_chat = None,
            credit_balance = 999.0,
            is_invited_to_start = False,
            are_policies_accepted = False,
            connect_key = "UPDATED-KEY",
        )

        apply_to_db_model(replacement, db_model)

        self.assertEqual(db_model.id, original_id)
        self.assertEqual(db_model.created_at, original_created_at)
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
        remote_data = stubs.domain.user_remote_data(
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
        existing = stubs.domain.user()
        remote_data = stubs.domain.user_remote_data(
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
        existing = replace(stubs.domain.user(), telegram_chat_id = None)
        remote_data = stubs.domain.user_remote_data(telegram_chat_id = "remote-chat")

        result = apply_remote_data(existing, remote_data)

        self.assertEqual(result.telegram_chat_id, "remote-chat")

    def test_apply_remote_data_fills_missing_full_name(self):
        existing = stubs.domain.user(
            full_name = None,
            connect_key = "CONN-KEY-0001",
        )
        remote_data = stubs.domain.user_remote_data(full_name = "Remote Name")

        result = apply_remote_data(existing, remote_data)

        self.assertEqual(result.full_name, "Remote Name")
