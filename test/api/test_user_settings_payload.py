import unittest

import stubs


class UserSettingsPayloadTest(unittest.TestCase):

    def test_basic_creation_with_all_fields(self):
        """Test creating payload with all fields provided"""
        payload = stubs.api.user_settings_payload(
            full_name = "Test User",
            about_me = "About",
            custom_prompt = "Prompt",
            open_ai_key = "sk-abc123",
            anthropic_key = "sk-ant-def456",
            google_ai_key = "google-key",
            perplexity_key = "pplx-ghi789",
            replicate_key = "r8_jkl012",
            rapid_api_key = "mno345",
            coinmarketcap_key = "pqr678-stu-901",
            twelve_data_api_key = "twelve-data-123",
            x_key = "x-vwx234",
            x_ai_key = "xai-yza567",
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_copywriting = "gpt-4o-mini",
            tool_choice_vision = "gpt-4o",
            tool_choice_images_gen = "dall-e-3",
            tool_choice_search = "perplexity-search",
            tool_choice_api_fiat_exchange = "rapid-api-fiat",
            tool_choice_api_crypto_exchange = "coinmarketcap-api",
            tool_choice_api_twitter = "rapid-api-twitter",
        )

        self.assertEqual(payload.full_name, "Test User")
        self.assertEqual(payload.about_me, "About")
        self.assertEqual(payload.custom_prompt, "Prompt")
        self.assertEqual(payload.open_ai_key, "sk-abc123")
        self.assertEqual(payload.anthropic_key, "sk-ant-def456")
        self.assertEqual(payload.google_ai_key, "google-key")
        self.assertEqual(payload.perplexity_key, "pplx-ghi789")
        self.assertEqual(payload.replicate_key, "r8_jkl012")
        self.assertEqual(payload.rapid_api_key, "mno345")
        self.assertEqual(payload.coinmarketcap_key, "pqr678-stu-901")
        self.assertEqual(payload.twelve_data_api_key, "twelve-data-123")
        self.assertEqual(payload.x_key, "x-vwx234")
        self.assertEqual(payload.x_ai_key, "xai-yza567")
        self.assertEqual(payload.tool_choice_chat, "gpt-4o")
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertEqual(payload.tool_choice_copywriting, "gpt-4o-mini")
        self.assertEqual(payload.tool_choice_vision, "gpt-4o")
        self.assertEqual(payload.tool_choice_hearing, "whisper-1")
        self.assertEqual(payload.tool_choice_images_gen, "dall-e-3")
        self.assertEqual(payload.tool_choice_videos_gen, "prunaai/p-video")
        self.assertEqual(payload.tool_choice_search, "perplexity-search")
        self.assertEqual(payload.tool_choice_embedding, "text-embedding-3-large")
        self.assertEqual(payload.tool_choice_api_fiat_exchange, "rapid-api-fiat")
        self.assertEqual(payload.tool_choice_api_crypto_exchange, "coinmarketcap-api")
        self.assertEqual(payload.tool_choice_api_stock_quote, "quote")
        self.assertEqual(payload.tool_choice_api_twitter, "rapid-api-twitter")
        self.assertTrue(payload.are_policies_accepted)

    def test_partial_creation_with_some_fields(self):
        """Test creating payload with only some fields provided"""
        payload = stubs.api.user_settings_payload(
            full_name = None,
            about_me = None,
            custom_prompt = None,
            open_ai_key = "sk-abc123",
            anthropic_key = "sk-ant-def456",
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = None,
            tool_choice_copywriting = None,
            tool_choice_vision = "claude-3-7-sonnet-latest",
            tool_choice_hearing = None,
            tool_choice_images_gen = None,
            tool_choice_videos_gen = None,
            tool_choice_search = None,
            tool_choice_embedding = None,
            tool_choice_api_fiat_exchange = None,
            tool_choice_api_crypto_exchange = None,
            tool_choice_api_stock_quote = None,
            tool_choice_api_twitter = None,
            are_policies_accepted = None,
        )

        self.assertEqual(payload.open_ai_key, "sk-abc123")
        self.assertEqual(payload.anthropic_key, "sk-ant-def456")
        self.assertEqual(payload.tool_choice_chat, "gpt-4o")
        self.assertEqual(payload.tool_choice_vision, "claude-3-7-sonnet-latest")
        self.assertIsNone(payload.perplexity_key)
        self.assertIsNone(payload.replicate_key)
        self.assertIsNone(payload.rapid_api_key)
        self.assertIsNone(payload.coinmarketcap_key)
        self.assertIsNone(payload.twelve_data_api_key)
        self.assertIsNone(payload.x_key)
        self.assertIsNone(payload.x_ai_key)
        self.assertIsNone(payload.tool_choice_reasoning)
        self.assertIsNone(payload.tool_choice_copywriting)
        self.assertIsNone(payload.tool_choice_hearing)
        self.assertIsNone(payload.tool_choice_images_gen)
        self.assertIsNone(payload.tool_choice_videos_gen)
        self.assertIsNone(payload.tool_choice_search)
        self.assertIsNone(payload.tool_choice_embedding)
        self.assertIsNone(payload.tool_choice_api_fiat_exchange)
        self.assertIsNone(payload.tool_choice_api_crypto_exchange)
        self.assertIsNone(payload.tool_choice_api_stock_quote)
        self.assertIsNone(payload.tool_choice_api_twitter)

    def test_string_trimming_validation(self):
        """Test that string fields are properly trimmed"""
        payload = stubs.api.user_settings_payload(
            open_ai_key = "  sk-abc123  ",
            anthropic_key = "\tsk-ant-def456\n",
            perplexity_key = " pplx-ghi789 ",
            tool_choice_chat = "  gpt-4o  ",
            tool_choice_reasoning = "\tclaude-3-7-sonnet-latest\n",
            tool_choice_vision = " gpt-4o ",
            tool_choice_hearing = "  whisper-1  ",
            tool_choice_images_gen = "\tdall-e-3\n",
            tool_choice_videos_gen = "  prunaai/p-video\n",
            tool_choice_search = " perplexity-search ",
            tool_choice_embedding = "  text-embedding-3-large  ",
        )

        self.assertEqual(payload.open_ai_key, "sk-abc123")
        self.assertEqual(payload.anthropic_key, "sk-ant-def456")
        self.assertEqual(payload.perplexity_key, "pplx-ghi789")
        self.assertEqual(payload.tool_choice_chat, "gpt-4o")
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertEqual(payload.tool_choice_vision, "gpt-4o")
        self.assertEqual(payload.tool_choice_hearing, "whisper-1")
        self.assertEqual(payload.tool_choice_images_gen, "dall-e-3")
        self.assertEqual(payload.tool_choice_videos_gen, "prunaai/p-video")
        self.assertEqual(payload.tool_choice_search, "perplexity-search")
        self.assertEqual(payload.tool_choice_embedding, "text-embedding-3-large")

    def test_empty_strings_after_trimming(self):
        """Test that empty strings after trimming remain empty strings"""
        payload = stubs.api.user_settings_payload(
            open_ai_key = "   ",  # spaces only
            anthropic_key = "\t\n",  # tabs and newlines
            perplexity_key = "",  # already empty
            tool_choice_chat = "   ",  # spaces only
            tool_choice_reasoning = "\t\n",  # tabs and newlines
            tool_choice_vision = "",  # already empty
            tool_choice_hearing = "   ",
            tool_choice_images_gen = "\t\n",
            tool_choice_videos_gen = "  ",
            tool_choice_search = "",
        )

        # after trimming, these should all be empty strings
        self.assertEqual(payload.open_ai_key, "")
        self.assertEqual(payload.anthropic_key, "")
        self.assertEqual(payload.perplexity_key, "")
        self.assertEqual(payload.tool_choice_chat, "")
        self.assertEqual(payload.tool_choice_reasoning, "")
        self.assertEqual(payload.tool_choice_vision, "")
        self.assertEqual(payload.tool_choice_hearing, "")
        self.assertEqual(payload.tool_choice_images_gen, "")
        self.assertEqual(payload.tool_choice_videos_gen, "")
        self.assertEqual(payload.tool_choice_search, "")

    def test_none_values_preserved(self):
        """Test that None values are preserved and not converted"""
        payload = stubs.api.user_settings_payload(
            open_ai_key = None,
            anthropic_key = "sk-ant-123",
            tool_choice_chat = None,
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_vision = None,
        )

        self.assertIsNone(payload.open_ai_key)
        self.assertEqual(payload.anthropic_key, "sk-ant-123")
        self.assertIsNone(payload.tool_choice_chat)
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertIsNone(payload.tool_choice_vision)
        self.assertEqual(payload.tool_choice_hearing, "whisper-1")

    def test_empty_payload(self):
        """Test creating a payload with every optional field set to None"""
        payload = stubs.api.user_settings_payload(
            full_name = None,
            about_me = None,
            custom_prompt = None,
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
            tool_choice_chat = None,
            tool_choice_reasoning = None,
            tool_choice_copywriting = None,
            tool_choice_vision = None,
            tool_choice_hearing = None,
            tool_choice_images_gen = None,
            tool_choice_videos_gen = None,
            tool_choice_search = None,
            tool_choice_embedding = None,
            tool_choice_api_fiat_exchange = None,
            tool_choice_api_crypto_exchange = None,
            tool_choice_api_stock_quote = None,
            tool_choice_api_twitter = None,
            are_policies_accepted = None,
        )

        self.assertTrue(all(value is None for value in payload.model_dump().values()))

    def test_tool_choice_only_payload(self):
        """Test creating payload with only tool choice fields"""
        payload = stubs.api.user_settings_payload(
            full_name = None,
            about_me = None,
            custom_prompt = None,
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_copywriting = None,
            tool_choice_vision = "gpt-4o",
            tool_choice_hearing = None,
            tool_choice_images_gen = "dall-e-3",
            tool_choice_search = "perplexity-search",
            tool_choice_embedding = None,
            tool_choice_api_fiat_exchange = None,
            tool_choice_api_crypto_exchange = None,
            tool_choice_api_stock_quote = None,
            tool_choice_api_twitter = None,
            are_policies_accepted = None,
        )

        # API keys should be None
        self.assertIsNone(payload.open_ai_key)
        self.assertIsNone(payload.anthropic_key)
        self.assertIsNone(payload.perplexity_key)
        self.assertIsNone(payload.replicate_key)
        self.assertIsNone(payload.rapid_api_key)
        self.assertIsNone(payload.coinmarketcap_key)
        self.assertIsNone(payload.twelve_data_api_key)
        self.assertIsNone(payload.x_key)
        self.assertIsNone(payload.x_ai_key)

        # tool choices should be set
        self.assertEqual(payload.tool_choice_chat, "gpt-4o")
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertEqual(payload.tool_choice_vision, "gpt-4o")
        self.assertEqual(payload.tool_choice_images_gen, "dall-e-3")
        self.assertEqual(payload.tool_choice_videos_gen, "prunaai/p-video")
        self.assertEqual(payload.tool_choice_search, "perplexity-search")

        # unset tool choices should be None
        self.assertIsNone(payload.tool_choice_copywriting)
        self.assertIsNone(payload.tool_choice_hearing)
        self.assertIsNone(payload.tool_choice_embedding)
        self.assertIsNone(payload.tool_choice_api_fiat_exchange)
        self.assertIsNone(payload.tool_choice_api_crypto_exchange)
        self.assertIsNone(payload.tool_choice_api_stock_quote)
        self.assertIsNone(payload.tool_choice_api_twitter)
