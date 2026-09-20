import unittest
from dataclasses import replace

import stubs

from api.mapper.user_api_mapper import apply_to_domain, domain_to_api
from util.functions import mask_secret


class UserMapperTest(unittest.TestCase):

    def test_apply_to_domain_with_all_fields(self):
        user = stubs.domain.user()
        payload = stubs.api.user_settings_payload(
            open_ai_key = "sk-new123",
            anthropic_key = "sk-ant-new456",
            google_ai_key = "google-new789",
            perplexity_key = "pplx-new789",
            replicate_key = "r8_new012",
            rapid_api_key = "rapid-new345",
            coinmarketcap_key = "cmc-new678",
            twelve_data_api_key = "twelve-data-new",
            x_key = "x-new901",
            x_ai_key = "xai-new234",
            tool_choice_chat = "gpt-4o-mini",
            tool_choice_reasoning = "claude-3-opus-latest",
            tool_choice_copywriting = "gpt-4o",
            tool_choice_vision = "gpt-4o-mini",
            tool_choice_hearing = "whisper-1-turbo",
            tool_choice_images_gen = "dall-e-3-hd",
            tool_choice_videos_gen = "google/veo-3.1",
            tool_choice_search = "perplexity-pro",
            tool_choice_embedding = "text-embedding-3-small",
            tool_choice_api_fiat_exchange = "new-fiat-api",
            tool_choice_api_crypto_exchange = "new-crypto-api",
            tool_choice_api_stock_quote = "new-stock-api",
            tool_choice_api_twitter = "new-twitter-api",
        )

        user_save = apply_to_domain(payload, user)
        # check that all payload fields were applied

        self.assertEqual(user_save.open_ai_key.get_secret_value() if user_save.open_ai_key else None, payload.open_ai_key)
        self.assertEqual(user_save.anthropic_key.get_secret_value() if user_save.anthropic_key else None, payload.anthropic_key)
        self.assertEqual(user_save.google_ai_key.get_secret_value() if user_save.google_ai_key else None, payload.google_ai_key)
        self.assertEqual(user_save.perplexity_key.get_secret_value() if user_save.perplexity_key else None, payload.perplexity_key)  # ruff: ignore[line-too-long]
        self.assertEqual(user_save.replicate_key.get_secret_value() if user_save.replicate_key else None, payload.replicate_key)
        self.assertEqual(user_save.rapid_api_key.get_secret_value() if user_save.rapid_api_key else None, payload.rapid_api_key)
        self.assertEqual(user_save.coinmarketcap_key.get_secret_value() if user_save.coinmarketcap_key else None, payload.coinmarketcap_key)  # ruff: ignore[line-too-long]
        self.assertEqual(user_save.twelve_data_api_key.get_secret_value() if user_save.twelve_data_api_key else None, payload.twelve_data_api_key)  # ruff: ignore[line-too-long]
        self.assertEqual(user_save.x_key.get_secret_value() if user_save.x_key else None, payload.x_key)
        self.assertEqual(user_save.x_ai_key.get_secret_value() if user_save.x_ai_key else None, payload.x_ai_key)
        self.assertEqual(user_save.tool_choice_chat, payload.tool_choice_chat)
        self.assertEqual(user_save.tool_choice_reasoning, payload.tool_choice_reasoning)
        self.assertEqual(user_save.tool_choice_copywriting, payload.tool_choice_copywriting)
        self.assertEqual(user_save.tool_choice_vision, payload.tool_choice_vision)
        self.assertEqual(user_save.tool_choice_hearing, payload.tool_choice_hearing)
        self.assertEqual(user_save.tool_choice_images_gen, payload.tool_choice_images_gen)
        self.assertEqual(user_save.tool_choice_videos_gen, payload.tool_choice_videos_gen)
        self.assertEqual(user_save.tool_choice_search, payload.tool_choice_search)
        self.assertEqual(user_save.tool_choice_embedding, payload.tool_choice_embedding)
        self.assertEqual(user_save.tool_choice_api_fiat_exchange, payload.tool_choice_api_fiat_exchange)
        self.assertEqual(user_save.tool_choice_api_crypto_exchange, payload.tool_choice_api_crypto_exchange)
        self.assertEqual(user_save.tool_choice_api_stock_quote, payload.tool_choice_api_stock_quote)
        self.assertEqual(user_save.tool_choice_api_twitter, payload.tool_choice_api_twitter)
        self.assertTrue(user_save.are_policies_accepted)
        # check that domain-only fields remain the same
        self.assertEqual(user_save.id, user.id)
        self.assertEqual(user_save.telegram_username, user.telegram_username)
        self.assertEqual(user_save.is_on_waitlist, user.is_on_waitlist)
        self.assertEqual(user_save.is_invited_to_start, user.is_invited_to_start)

    def test_apply_to_domain_with_overrides(self):
        user = stubs.domain.user()
        payload = stubs.api.user_settings_payload(
            open_ai_key = "sk-new123",
            tool_choice_chat = "gpt-4o-mini",
        )

        user_save = apply_to_domain(payload, user)
        # check that explicitly overridden fields were applied

        self.assertEqual(user_save.open_ai_key.get_secret_value() if user_save.open_ai_key else None, payload.open_ai_key)
        self.assertEqual(user_save.tool_choice_chat, payload.tool_choice_chat)
        # check that the remaining fields use the curated payload values
        self.assertEqual(
            user_save.anthropic_key.get_secret_value() if user_save.anthropic_key else None,
            payload.anthropic_key,
        )
        self.assertEqual(
            user_save.google_ai_key.get_secret_value() if user_save.google_ai_key else None,
            payload.google_ai_key,
        )
        self.assertEqual(user_save.tool_choice_reasoning, payload.tool_choice_reasoning)

    def test_apply_to_domain_with_empty_strings(self):
        user = stubs.domain.user()
        payload = stubs.api.user_settings_payload(
            open_ai_key = "   ",
            tool_choice_chat = "",
        )

        user_save = apply_to_domain(payload, user)
        # check that empty and whitespace-only strings become None

        self.assertIsNone(user_save.open_ai_key)
        self.assertIsNone(user_save.tool_choice_chat)

    def test_apply_to_domain_with_full_name(self):
        user = stubs.domain.user()
        # set a new full name
        payload_set = stubs.api.user_settings_payload(full_name = "New Name")
        user_save = apply_to_domain(payload_set, user)
        self.assertEqual(user_save.full_name, payload_set.full_name)

        # clear the full name with an empty string
        payload_clear = stubs.api.user_settings_payload(full_name = "")
        user_save = apply_to_domain(payload_clear, user)
        self.assertIsNone(user_save.full_name)

    def test_apply_to_domain_with_about_me(self):
        user = stubs.domain.user()
        # set a new about-me value
        payload_set = stubs.api.user_settings_payload(about_me = "I enjoy hiking and photography")
        user_save = apply_to_domain(payload_set, user)
        self.assertEqual(
            user_save.about_me.get_secret_value() if user_save.about_me else None,
            payload_set.about_me,
        )

        # clear the about-me value with an empty string
        payload_clear = stubs.api.user_settings_payload(about_me = "")
        user_save = apply_to_domain(payload_clear, user)
        self.assertIsNone(user_save.about_me)

    def test_apply_to_domain_with_custom_prompt(self):
        user = stubs.domain.user()
        # set a new custom prompt
        payload_set = stubs.api.user_settings_payload(custom_prompt = "Always respond in formal English")
        user_save = apply_to_domain(payload_set, user)
        self.assertEqual(
            user_save.custom_prompt.get_secret_value() if user_save.custom_prompt else None,
            payload_set.custom_prompt,
        )

        # clear the custom prompt with an empty string
        payload_clear = stubs.api.user_settings_payload(custom_prompt = "")
        user_save = apply_to_domain(payload_clear, user)
        self.assertIsNone(user_save.custom_prompt)

    def test_domain_to_api_conversion(self):
        user = stubs.domain.user()

        masked_user = domain_to_api(user, is_sponsored = False)

        # check basic fields
        self.assertEqual(masked_user.id, user.id.hex)
        self.assertEqual(masked_user.full_name, user.full_name)
        # check that about_me is returned unmasked
        assert user.about_me is not None
        self.assertEqual(masked_user.about_me, user.about_me.get_secret_value())
        assert user.custom_prompt is not None
        # check that custom_prompt is returned unmasked
        self.assertEqual(masked_user.custom_prompt, user.custom_prompt.get_secret_value())
        self.assertEqual(masked_user.telegram_username, user.telegram_username)
        self.assertEqual(masked_user.telegram_chat_id, user.telegram_chat_id)
        self.assertEqual(masked_user.telegram_user_id, user.telegram_user_id)
        self.assertEqual(masked_user.whatsapp_user_id, user.whatsapp_user_id)
        assert user.whatsapp_phone_number is not None
        self.assertEqual(masked_user.whatsapp_phone_number, user.whatsapp_phone_number.get_secret_value())
        self.assertEqual(masked_user.credit_balance, user.credit_balance)
        self.assertEqual(masked_user.is_on_waitlist, user.is_on_waitlist)
        self.assertEqual(masked_user.is_invited_to_start, user.is_invited_to_start)
        self.assertEqual(masked_user.are_policies_accepted, user.are_policies_accepted)
        self.assertFalse(masked_user.is_sponsored)
        self.assertEqual(masked_user.group, user.group.value)
        self.assertEqual(masked_user.created_at, user.created_at.isoformat())
        # check that API keys are masked
        self.assertEqual(masked_user.open_ai_key, mask_secret(user.open_ai_key))
        self.assertEqual(masked_user.anthropic_key, mask_secret(user.anthropic_key))
        self.assertEqual(masked_user.google_ai_key, mask_secret(user.google_ai_key))
        self.assertEqual(masked_user.perplexity_key, mask_secret(user.perplexity_key))
        self.assertEqual(masked_user.replicate_key, mask_secret(user.replicate_key))
        self.assertEqual(masked_user.rapid_api_key, mask_secret(user.rapid_api_key))
        self.assertEqual(masked_user.coinmarketcap_key, mask_secret(user.coinmarketcap_key))
        self.assertEqual(masked_user.twelve_data_api_key, mask_secret(user.twelve_data_api_key))
        self.assertEqual(masked_user.x_key, mask_secret(user.x_key))
        self.assertEqual(masked_user.x_ai_key, mask_secret(user.x_ai_key))
        # check that tool choices are not masked
        self.assertEqual(masked_user.tool_choice_chat, user.tool_choice_chat)
        self.assertEqual(masked_user.tool_choice_reasoning, user.tool_choice_reasoning)
        self.assertEqual(masked_user.tool_choice_copywriting, user.tool_choice_copywriting)
        self.assertEqual(masked_user.tool_choice_vision, user.tool_choice_vision)
        self.assertEqual(masked_user.tool_choice_hearing, user.tool_choice_hearing)
        self.assertEqual(masked_user.tool_choice_images_gen, user.tool_choice_images_gen)
        self.assertEqual(masked_user.tool_choice_videos_gen, user.tool_choice_videos_gen)
        self.assertEqual(masked_user.tool_choice_search, user.tool_choice_search)
        self.assertEqual(masked_user.tool_choice_embedding, user.tool_choice_embedding)
        self.assertEqual(masked_user.tool_choice_api_fiat_exchange, user.tool_choice_api_fiat_exchange)
        self.assertEqual(masked_user.tool_choice_api_crypto_exchange, user.tool_choice_api_crypto_exchange)
        self.assertEqual(masked_user.tool_choice_api_stock_quote, user.tool_choice_api_stock_quote)
        self.assertEqual(masked_user.tool_choice_api_twitter, user.tool_choice_api_twitter)

    def test_domain_to_api_with_none_values(self):
        user = stubs.domain.user()
        user_with_nones = replace(
            user,
            about_me = None,
            custom_prompt = None,
            open_ai_key = None,
            tool_choice_chat = None,
            tool_choice_reasoning = None,
        )

        masked_user = domain_to_api(user_with_nones, is_sponsored = True)

        # check that None values remain None
        self.assertIsNone(masked_user.about_me)
        self.assertIsNone(masked_user.custom_prompt)
        self.assertIsNone(masked_user.open_ai_key)
        self.assertIsNone(masked_user.tool_choice_chat)
        self.assertIsNone(masked_user.tool_choice_reasoning)
        self.assertTrue(masked_user.is_sponsored)
        # check that non-None values are still processed
        self.assertIsNotNone(masked_user.anthropic_key)
        self.assertEqual(masked_user.tool_choice_copywriting, user.tool_choice_copywriting)
