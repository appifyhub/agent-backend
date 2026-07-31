import unittest

from api.model.user_settings_payload import UserSettingsPayload


class UserSettingsPayloadTest(unittest.TestCase):

    def test_basic_creation_with_all_fields(self):
        """Test creating payload with all fields provided"""
        payload = UserSettingsPayload(
            open_ai_key = "sk-abc123",
            anthropic_key = "sk-ant-def456",
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
            tool_choice_hearing = "whisper-1",
            tool_choice_images_gen = "dall-e-3",
            tool_choice_videos_gen = "prunaai/p-video",
            tool_choice_images_edit = "dall-e-2",
            tool_choice_search = "perplexity-search",
            tool_choice_embedding = "text-embedding-3-large",
            tool_choice_api_fiat_exchange = "rapid-api-fiat",
            tool_choice_api_crypto_exchange = "coinmarketcap-api",
            tool_choice_api_stock_quote = "quote",
            tool_choice_api_twitter = "rapid-api-twitter",
        )

        self.assertEqual(payload.open_ai_key, "sk-abc123")
        self.assertEqual(payload.anthropic_key, "sk-ant-def456")
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
        self.assertEqual(payload.tool_choice_images_edit, "dall-e-2")
        self.assertEqual(payload.tool_choice_search, "perplexity-search")
        self.assertEqual(payload.tool_choice_embedding, "text-embedding-3-large")
        self.assertEqual(payload.tool_choice_api_fiat_exchange, "rapid-api-fiat")
        self.assertEqual(payload.tool_choice_api_crypto_exchange, "coinmarketcap-api")
        self.assertEqual(payload.tool_choice_api_stock_quote, "quote")
        self.assertEqual(payload.tool_choice_api_twitter, "rapid-api-twitter")

    def test_partial_creation_with_some_fields(self):
        """Test creating payload with only some fields provided"""
        payload = UserSettingsPayload(
            open_ai_key = "sk-abc123",
            anthropic_key = "sk-ant-def456",
            tool_choice_chat = "gpt-4o",
            tool_choice_vision = "claude-3-7-sonnet-latest",
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
        self.assertIsNone(payload.tool_choice_images_edit)
        self.assertIsNone(payload.tool_choice_search)
        self.assertIsNone(payload.tool_choice_embedding)
        self.assertIsNone(payload.tool_choice_api_fiat_exchange)
        self.assertIsNone(payload.tool_choice_api_crypto_exchange)
        self.assertIsNone(payload.tool_choice_api_stock_quote)
        self.assertIsNone(payload.tool_choice_api_twitter)

    def test_string_trimming_validation(self):
        """Test that string fields are properly trimmed"""
        payload = UserSettingsPayload(
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
        payload = UserSettingsPayload(
            open_ai_key = "   ",  # Spaces only
            anthropic_key = "\t\n",  # Tabs and newlines
            perplexity_key = "",  # Already empty
            tool_choice_chat = "   ",  # Spaces only
            tool_choice_reasoning = "\t\n",  # Tabs and newlines
            tool_choice_vision = "",  # Already empty
            tool_choice_hearing = "   ",
            tool_choice_images_gen = "\t\n",
            tool_choice_videos_gen = "  ",
            tool_choice_search = "",
        )

        # After trimming, these should all be empty strings
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
        payload = UserSettingsPayload(
            open_ai_key = None,
            anthropic_key = "sk-ant-123",
            tool_choice_chat = None,
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_vision = None,
            tool_choice_hearing = "whisper-1",
        )

        self.assertIsNone(payload.open_ai_key)
        self.assertEqual(payload.anthropic_key, "sk-ant-123")
        self.assertIsNone(payload.tool_choice_chat)
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertIsNone(payload.tool_choice_vision)
        self.assertEqual(payload.tool_choice_hearing, "whisper-1")

    def test_empty_payload(self):
        """Test creating an empty payload (all defaults)"""
        payload = UserSettingsPayload()

        self.assertIsNone(payload.open_ai_key)
        self.assertIsNone(payload.anthropic_key)
        self.assertIsNone(payload.perplexity_key)
        self.assertIsNone(payload.replicate_key)
        self.assertIsNone(payload.rapid_api_key)
        self.assertIsNone(payload.coinmarketcap_key)
        self.assertIsNone(payload.twelve_data_api_key)
        self.assertIsNone(payload.x_key)
        self.assertIsNone(payload.x_ai_key)
        self.assertIsNone(payload.tool_choice_chat)
        self.assertIsNone(payload.tool_choice_reasoning)
        self.assertIsNone(payload.tool_choice_copywriting)
        self.assertIsNone(payload.tool_choice_vision)
        self.assertIsNone(payload.tool_choice_hearing)
        self.assertIsNone(payload.tool_choice_images_gen)
        self.assertIsNone(payload.tool_choice_videos_gen)
        self.assertIsNone(payload.tool_choice_images_edit)
        self.assertIsNone(payload.tool_choice_search)
        self.assertIsNone(payload.tool_choice_embedding)
        self.assertIsNone(payload.tool_choice_api_fiat_exchange)
        self.assertIsNone(payload.tool_choice_api_crypto_exchange)
        self.assertIsNone(payload.tool_choice_api_stock_quote)
        self.assertIsNone(payload.tool_choice_api_twitter)

    def test_tool_choice_only_payload(self):
        """Test creating payload with only tool choice fields"""
        payload = UserSettingsPayload(
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_vision = "gpt-4o",
            tool_choice_images_gen = "dall-e-3",
            tool_choice_videos_gen = "prunaai/p-video",
            tool_choice_search = "perplexity-search",
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

        # Tool choices should be set
        self.assertEqual(payload.tool_choice_chat, "gpt-4o")
        self.assertEqual(payload.tool_choice_reasoning, "claude-3-7-sonnet-latest")
        self.assertEqual(payload.tool_choice_vision, "gpt-4o")
        self.assertEqual(payload.tool_choice_images_gen, "dall-e-3")
        self.assertEqual(payload.tool_choice_videos_gen, "prunaai/p-video")
        self.assertEqual(payload.tool_choice_search, "perplexity-search")

        # Unset tool choices should be None
        self.assertIsNone(payload.tool_choice_copywriting)
        self.assertIsNone(payload.tool_choice_hearing)
        self.assertIsNone(payload.tool_choice_images_edit)
        self.assertIsNone(payload.tool_choice_embedding)
        self.assertIsNone(payload.tool_choice_api_fiat_exchange)
        self.assertIsNone(payload.tool_choice_api_crypto_exchange)
        self.assertIsNone(payload.tool_choice_api_stock_quote)
        self.assertIsNone(payload.tool_choice_api_twitter)
