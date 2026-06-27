import unittest
from datetime import date
from uuid import UUID

from pydantic import SecretStr

from api.mapper.user_api_mapper import api_to_domain, domain_to_api
from api.model.user_settings_payload import UserSettingsPayload
from db.model.user import UserDB
from db.schema.user import User
from util.functions import mask_secret


class UserMapperTest(unittest.TestCase):

    user: User

    def setUp(self):
        self.user = User(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Test User",
            about_me = SecretStr("I love Python programming and enjoy hiking on weekends"),
            custom_prompt = SecretStr("Always respond concisely and in bullet points"),
            telegram_username = "testuser",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
            whatsapp_user_id = "15551234567",
            whatsapp_phone_number = SecretStr("15551234567"),
            open_ai_key = SecretStr("sk-test123"),
            anthropic_key = SecretStr("sk-ant-test456"),
            google_ai_key = SecretStr("google-test789"),
            perplexity_key = SecretStr("pplx-test789"),
            replicate_key = SecretStr("r8_test012"),
            rapid_api_key = SecretStr("rapid-test345"),
            coinmarketcap_key = SecretStr("cmc-test678"),
            x_key = SecretStr("x-test901"),
            x_ai_key = SecretStr("xai-test234"),
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_copywriting = "gpt-4o-mini",
            tool_choice_vision = "gpt-4o",
            tool_choice_hearing = "whisper-1",
            tool_choice_images_gen = "dall-e-3",
            tool_choice_images_edit = "dall-e-2",
            tool_choice_search = "perplexity-online",
            tool_choice_embedding = "text-embedding-3-large",
            tool_choice_api_fiat_exchange = "rapid-api-fiat",
            tool_choice_api_crypto_exchange = "coinmarketcap-crypto",
            tool_choice_api_twitter = "rapid-api-twitter",
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
            group = UserDB.Group.standard,
            created_at = date(2024, 1, 1),
        )

    def test_api_to_domain_with_all_fields(self):
        payload = UserSettingsPayload(
            open_ai_key = "sk-new123",
            anthropic_key = "sk-ant-new456",
            google_ai_key = "google-new789",
            perplexity_key = "pplx-new789",
            replicate_key = "r8_new012",
            rapid_api_key = "rapid-new345",
            coinmarketcap_key = "cmc-new678",
            x_key = "x-new901",
            x_ai_key = "xai-new234",
            tool_choice_chat = "gpt-4o-mini",
            tool_choice_reasoning = "claude-3-opus-latest",
            tool_choice_copywriting = "gpt-4o",
            tool_choice_vision = "gpt-4o-mini",
            tool_choice_hearing = "whisper-1-turbo",
            tool_choice_images_gen = "dall-e-3-hd",
            tool_choice_images_edit = "dall-e-3",
            tool_choice_search = "perplexity-pro",
            tool_choice_embedding = "text-embedding-3-small",
            tool_choice_api_fiat_exchange = "new-fiat-api",
            tool_choice_api_crypto_exchange = "new-crypto-api",
            tool_choice_api_twitter = "new-twitter-api",
            are_policies_accepted = True,
        )

        user_save = api_to_domain(payload, self.user)

        # Check that all fields were updated
        self.assertEqual(user_save.open_ai_key.get_secret_value() if user_save.open_ai_key else None, "sk-new123")
        self.assertEqual(user_save.anthropic_key.get_secret_value() if user_save.anthropic_key else None, "sk-ant-new456")
        self.assertEqual(user_save.google_ai_key.get_secret_value() if user_save.google_ai_key else None, "google-new789")
        self.assertEqual(user_save.perplexity_key.get_secret_value() if user_save.perplexity_key else None, "pplx-new789")
        self.assertEqual(user_save.replicate_key.get_secret_value() if user_save.replicate_key else None, "r8_new012")
        self.assertEqual(user_save.rapid_api_key.get_secret_value() if user_save.rapid_api_key else None, "rapid-new345")
        self.assertEqual(user_save.coinmarketcap_key.get_secret_value() if user_save.coinmarketcap_key else None, "cmc-new678")
        self.assertEqual(user_save.x_key.get_secret_value() if user_save.x_key else None, "x-new901")
        self.assertEqual(user_save.x_ai_key.get_secret_value() if user_save.x_ai_key else None, "xai-new234")
        self.assertEqual(user_save.tool_choice_chat, "gpt-4o-mini")
        self.assertEqual(user_save.tool_choice_reasoning, "claude-3-opus-latest")
        self.assertEqual(user_save.tool_choice_copywriting, "gpt-4o")
        self.assertEqual(user_save.tool_choice_vision, "gpt-4o-mini")
        self.assertEqual(user_save.tool_choice_hearing, "whisper-1-turbo")
        self.assertEqual(user_save.tool_choice_images_gen, "dall-e-3-hd")
        self.assertEqual(user_save.tool_choice_images_edit, "dall-e-3")
        self.assertEqual(user_save.tool_choice_search, "perplexity-pro")
        self.assertEqual(user_save.tool_choice_embedding, "text-embedding-3-small")
        self.assertEqual(user_save.tool_choice_api_fiat_exchange, "new-fiat-api")
        self.assertEqual(user_save.tool_choice_api_crypto_exchange, "new-crypto-api")
        self.assertEqual(user_save.tool_choice_api_twitter, "new-twitter-api")
        self.assertTrue(user_save.are_policies_accepted)

        # Check that non-updated fields remain the same
        self.assertEqual(user_save.id, self.user.id)
        self.assertEqual(user_save.full_name, self.user.full_name)
        self.assertEqual(user_save.telegram_username, self.user.telegram_username)
        self.assertEqual(user_save.is_on_waitlist, self.user.is_on_waitlist)
        self.assertEqual(user_save.is_invited_to_start, self.user.is_invited_to_start)

    def test_api_to_domain_with_partial_fields(self):
        payload = UserSettingsPayload(
            open_ai_key = "sk-new123",
            tool_choice_chat = "gpt-4o-mini",
        )

        user_save = api_to_domain(payload, self.user)

        # Check that provided fields were updated
        self.assertEqual(user_save.open_ai_key.get_secret_value() if user_save.open_ai_key else None, "sk-new123")
        self.assertEqual(user_save.tool_choice_chat, "gpt-4o-mini")

        # Check that non-provided fields remain unchanged
        self.assertEqual(user_save.anthropic_key, self.user.anthropic_key)
        self.assertEqual(user_save.google_ai_key, self.user.google_ai_key)
        self.assertEqual(user_save.tool_choice_reasoning, self.user.tool_choice_reasoning)

    def test_api_to_domain_with_empty_strings(self):
        payload = UserSettingsPayload(
            open_ai_key = "   ",  # whitespace only
            tool_choice_chat = "",  # empty string
        )

        user_save = api_to_domain(payload, self.user)

        # Check that empty/whitespace strings become None
        self.assertIsNone(user_save.open_ai_key)
        self.assertIsNone(user_save.tool_choice_chat)

    def test_api_to_domain_with_full_name(self):
        # Test setting a new full_name
        payload_set = UserSettingsPayload(
            full_name = "New Name",
        )
        user_save = api_to_domain(payload_set, self.user)
        self.assertEqual(user_save.full_name, "New Name")

        # Test clearing full_name with empty string
        payload_clear = UserSettingsPayload(
            full_name = "",
        )
        user_save = api_to_domain(payload_clear, self.user)
        self.assertIsNone(user_save.full_name)

        # Test that None in payload preserves existing value
        payload_none = UserSettingsPayload(
            open_ai_key = "sk-test",
        )
        user_save = api_to_domain(payload_none, self.user)
        self.assertEqual(user_save.full_name, self.user.full_name)

    def test_api_to_domain_with_about_me(self):
        # Test setting a new about_me
        payload_set = UserSettingsPayload(
            about_me = "I enjoy hiking and photography",
        )
        user_save = api_to_domain(payload_set, self.user)
        self.assertEqual(
            user_save.about_me.get_secret_value() if user_save.about_me else None,
            "I enjoy hiking and photography",
        )

        # Test clearing about_me with empty string
        payload_clear = UserSettingsPayload(
            about_me = "",
        )
        user_save = api_to_domain(payload_clear, self.user)
        self.assertIsNone(user_save.about_me)

        # Test that None in payload preserves existing value
        payload_none = UserSettingsPayload(
            open_ai_key = "sk-test",
        )
        user_save = api_to_domain(payload_none, self.user)
        self.assertEqual(user_save.about_me, self.user.about_me)

    def test_api_to_domain_with_custom_prompt(self):
        # Test setting a new custom_prompt
        payload_set = UserSettingsPayload(
            custom_prompt = "Always respond in formal English",
        )
        user_save = api_to_domain(payload_set, self.user)
        self.assertEqual(
            user_save.custom_prompt.get_secret_value() if user_save.custom_prompt else None,
            "Always respond in formal English",
        )

        # Test clearing custom_prompt with empty string
        payload_clear = UserSettingsPayload(
            custom_prompt = "",
        )
        user_save = api_to_domain(payload_clear, self.user)
        self.assertIsNone(user_save.custom_prompt)

        # Test that None in payload preserves existing value
        payload_none = UserSettingsPayload(
            open_ai_key = "sk-test",
        )
        user_save = api_to_domain(payload_none, self.user)
        self.assertEqual(user_save.custom_prompt, self.user.custom_prompt)

    def test_domain_to_api_conversion(self):
        masked_user = domain_to_api(self.user, is_sponsored = False)

        # Check basic fields
        self.assertEqual(masked_user.id, self.user.id.hex)
        self.assertEqual(masked_user.full_name, self.user.full_name)
        # Check that about_me is NOT masked (returned as-is)
        assert self.user.about_me is not None
        self.assertEqual(
            masked_user.about_me,
            self.user.about_me.get_secret_value(),
        )
        # Check that custom_prompt is NOT masked (returned as-is)
        assert self.user.custom_prompt is not None
        self.assertEqual(
            masked_user.custom_prompt,
            self.user.custom_prompt.get_secret_value(),
        )
        self.assertEqual(masked_user.telegram_username, self.user.telegram_username)
        self.assertEqual(masked_user.telegram_chat_id, self.user.telegram_chat_id)
        self.assertEqual(masked_user.telegram_user_id, self.user.telegram_user_id)
        self.assertEqual(masked_user.whatsapp_user_id, self.user.whatsapp_user_id)
        assert self.user.whatsapp_phone_number is not None
        self.assertEqual(masked_user.whatsapp_phone_number, self.user.whatsapp_phone_number.get_secret_value())
        self.assertEqual(masked_user.credit_balance, self.user.credit_balance)
        self.assertEqual(masked_user.is_on_waitlist, self.user.is_on_waitlist)
        self.assertEqual(masked_user.is_invited_to_start, self.user.is_invited_to_start)
        self.assertEqual(masked_user.are_policies_accepted, self.user.are_policies_accepted)
        self.assertFalse(masked_user.is_sponsored)
        self.assertEqual(masked_user.group, self.user.group.value)
        self.assertEqual(masked_user.created_at, self.user.created_at.isoformat())

        # Check that API keys are masked
        self.assertEqual(masked_user.open_ai_key, mask_secret(self.user.open_ai_key))
        self.assertEqual(masked_user.anthropic_key, mask_secret(self.user.anthropic_key))
        self.assertEqual(masked_user.google_ai_key, mask_secret(self.user.google_ai_key))
        self.assertEqual(masked_user.perplexity_key, mask_secret(self.user.perplexity_key))
        self.assertEqual(masked_user.replicate_key, mask_secret(self.user.replicate_key))
        self.assertEqual(masked_user.rapid_api_key, mask_secret(self.user.rapid_api_key))
        self.assertEqual(masked_user.coinmarketcap_key, mask_secret(self.user.coinmarketcap_key))
        self.assertEqual(masked_user.x_key, mask_secret(self.user.x_key))
        self.assertEqual(masked_user.x_ai_key, mask_secret(self.user.x_ai_key))

        # Check that tool choices are not masked
        self.assertEqual(masked_user.tool_choice_chat, self.user.tool_choice_chat)
        self.assertEqual(masked_user.tool_choice_reasoning, self.user.tool_choice_reasoning)
        self.assertEqual(masked_user.tool_choice_copywriting, self.user.tool_choice_copywriting)
        self.assertEqual(masked_user.tool_choice_vision, self.user.tool_choice_vision)
        self.assertEqual(masked_user.tool_choice_hearing, self.user.tool_choice_hearing)
        self.assertEqual(masked_user.tool_choice_images_gen, self.user.tool_choice_images_gen)
        self.assertEqual(masked_user.tool_choice_images_edit, self.user.tool_choice_images_edit)
        self.assertEqual(masked_user.tool_choice_search, self.user.tool_choice_search)
        self.assertEqual(masked_user.tool_choice_embedding, self.user.tool_choice_embedding)
        self.assertEqual(masked_user.tool_choice_api_fiat_exchange, self.user.tool_choice_api_fiat_exchange)
        self.assertEqual(masked_user.tool_choice_api_crypto_exchange, self.user.tool_choice_api_crypto_exchange)
        self.assertEqual(masked_user.tool_choice_api_twitter, self.user.tool_choice_api_twitter)

    def test_domain_to_api_with_none_values(self):
        user_with_nones = self.user.model_copy(
            update = {
                "about_me": None,
                "custom_prompt": None,
                "open_ai_key": None,
                "tool_choice_chat": None,
                "tool_choice_reasoning": None,
            },
        )

        masked_user = domain_to_api(user_with_nones, is_sponsored = True)

        # Check that None values remain None
        self.assertIsNone(masked_user.about_me)
        self.assertIsNone(masked_user.custom_prompt)
        self.assertIsNone(masked_user.open_ai_key)
        self.assertIsNone(masked_user.tool_choice_chat)
        self.assertIsNone(masked_user.tool_choice_reasoning)
        self.assertTrue(masked_user.is_sponsored)

        # Check that non-None values are still processed
        self.assertIsNotNone(masked_user.anthropic_key)
        self.assertEqual(masked_user.tool_choice_copywriting, self.user.tool_choice_copywriting)
