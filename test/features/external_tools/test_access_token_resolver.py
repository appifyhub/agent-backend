import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from uuid import UUID

import stubs
from pydantic import SecretStr

from di.di import DI
from features.external_tools.access_token_resolver import AccessTokenResolver, ResolvedToken, TokenResolutionError
from features.external_tools.external_tool_library import GPT_5_6_TERRA
from features.external_tools.external_tool_provider_library import (
    ANTHROPIC,
    COINMARKETCAP,
    GOOGLE_AI,
    OPEN_AI,
    PERPLEXITY,
    RAPID_API,
    REPLICATE,
    TWELVE_DATA,
    XAI,
    X,
)
from features.integrations.integration_config import SYSTEM_AGENTS
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.users.user_repo import UserRepository


class AccessTokenResolverTest(unittest.TestCase):

    mock_user_repo: UserRepository
    mock_sponsorship_repo: SponsorshipRepository
    mock_di: DI

    def setUp(self):
        self.mock_user_repo = Mock(spec = UserRepository)
        self.mock_sponsorship_repo = Mock(spec = SponsorshipRepository)
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_repo = self.mock_user_repo
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo

    def test_init_with_user_object_success(self):
        self.mock_di.invoker = stubs.domain.user()
        resolver = AccessTokenResolver(self.mock_di)

        # Should not raise an exception
        self.assertIsNotNone(resolver)
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.get.assert_not_called()

    def test_get_access_token_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.open_ai_key.get_secret_value())
        self.assertFalse(token.uses_credits)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_not_called()

    def test_get_access_token_success_user_no_token_has_sponsorship(self):
        user_without_token = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsor_user = stubs.domain.user(id = UUID(int = 2))
        sponsorship = stubs.domain.sponsorship(sponsor_id = sponsor_user.id, receiver_id = user_without_token.id)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = sponsor_user

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), sponsor_user.open_ai_key.get_secret_value())
        self.assertFalse(token.uses_credits)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.get.assert_called_once_with(sponsorship.sponsor_id)

    def test_get_access_token_failure_pending_sponsorship_not_accepted(self):
        user_without_token = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsorship = stubs.domain.sponsorship(sponsor_id = UUID(int = 2), receiver_id = user_without_token.id)
        pending_sponsorship = replace(sponsorship, accepted_at = None)
        self.mock_di.invoker = user_without_token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [pending_sponsorship]

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        self.mock_user_repo.get.assert_not_called()

    def test_get_access_token_failure_user_no_token_no_sponsorship(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        assert token is None
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)

    def test_get_access_token_failure_user_no_token_sponsor_not_found(self):
        user_without_token = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsorship = stubs.domain.sponsorship(sponsor_id = UUID(int = 2), receiver_id = user_without_token.id)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = None

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        assert token is None
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.get.assert_called_once_with(sponsorship.sponsor_id)

    def test_get_access_token_failure_user_no_token_sponsor_no_token(self):
        user_without_token = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsor_without_token = stubs.domain.user(id = UUID(int = 2), open_ai_key = None, credit_balance = 0.0)
        sponsorship = stubs.domain.sponsorship(sponsor_id = sponsor_without_token.id, receiver_id = user_without_token.id)
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = sponsor_without_token

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(OPEN_AI)

        assert token is None

    def test_get_access_token_failure_unsupported_provider(self):
        self.mock_di.invoker = stubs.domain.user()
        # Set up mock to return empty list to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        # Create a truly unsupported provider
        unsupported_provider = stubs.domain.external_tool_provider(id = "unsupported")

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(unsupported_provider)

        self.assertIsNone(token)

    def test_get_access_token_for_tool_success(self):
        self.mock_di.invoker = stubs.domain.user()
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)
        tool = GPT_5_6_TERRA

        token = resolver.get_access_token_for_tool(tool)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_success(self):
        self.mock_di.invoker = stubs.domain.user()
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.require_access_token(OPEN_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_failure_raises_exception(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)

        with self.assertRaises(TokenResolutionError) as context:
            resolver.require_access_token(OPEN_AI)

        self.assertIn(f"Unable to resolve an access token for '{OPEN_AI.name}'", str(context.exception))

    def test_require_access_token_for_tool_success(self):
        self.mock_di.invoker = stubs.domain.user()
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)
        tool = GPT_5_6_TERRA

        token = resolver.require_access_token_for_tool(tool)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_for_tool_failure_raises_exception(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)
        tool = GPT_5_6_TERRA

        with self.assertRaises(TokenResolutionError):
            resolver.require_access_token_for_tool(tool)

    def test_get_access_token_anthropic_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(ANTHROPIC)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.anthropic_key.get_secret_value())

    def test_get_access_token_perplexity_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(PERPLEXITY)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.perplexity_key.get_secret_value())

    def test_get_access_token_replicate_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(REPLICATE)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.replicate_key.get_secret_value())

    def test_get_access_token_rapid_api_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(RAPID_API)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.rapid_api_key.get_secret_value())

    def test_get_access_token_coinmarketcap_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(COINMARKETCAP)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.coinmarketcap_key.get_secret_value())

    def test_get_access_token_twelve_data_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(TWELVE_DATA)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.twelve_data_api_key.get_secret_value())
        self.assertFalse(token.uses_credits)
        self.mock_sponsorship_repo.get_all_by_receiver.assert_not_called()

    def test_get_access_token_twelve_data_success_sponsor_has_token(self):
        user_without_token = stubs.domain.user(id = UUID(int = 1), twelve_data_api_key = None, credit_balance = 0.0)
        sponsor_user = stubs.domain.user(id = UUID(int = 2))
        sponsorship = stubs.domain.sponsorship(sponsor_id = sponsor_user.id, receiver_id = user_without_token.id)
        self.mock_di.invoker = user_without_token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = sponsor_user

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(TWELVE_DATA)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), sponsor_user.twelve_data_api_key.get_secret_value())
        self.assertEqual(token.payer_id, sponsor_user.id)
        self.assertFalse(token.uses_credits)

    def test_get_access_token_x_api_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(X)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.x_key.get_secret_value())

    def test_get_access_token_x_ai_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(XAI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.x_ai_key.get_secret_value())

    def test_get_access_token_google_ai_success_user_has_direct_token(self):
        self.mock_di.invoker = stubs.domain.user()
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(GOOGLE_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.mock_di.invoker.google_ai_key.get_secret_value())

    def test_get_access_token_uses_platform_key_when_user_has_credits(self):
        user_with_credits = stubs.domain.user(
            open_ai_key = None,
                    )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key.get_secret_value.return_value = "platform-openai-key"
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
        self.assertTrue(token.uses_credits)

    def test_get_access_token_system_agents_use_platform_key_without_credits(self):
        resolver = AccessTokenResolver(self.mock_di)

        for agent in SYSTEM_AGENTS:
            with self.subTest(agent_id = agent.id):
                system_agent = stubs.domain.user(
                    id = agent.id,
                    open_ai_key = SecretStr("stale-agent-key"),
                    credit_balance = 0.0,
                )
                self.mock_di.invoker = system_agent
                self.mock_sponsorship_repo.reset_mock()

                with patch("features.external_tools.access_token_resolver.config") as mock_config:
                    mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
                    token = resolver.get_access_token(OPEN_AI)

                assert token is not None
                self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
                self.assertEqual(token.payer_id, agent.id)
                self.assertFalse(token.uses_credits)
                self.mock_sponsorship_repo.get_all_by_receiver.assert_not_called()

    def test_get_access_token_returns_none_when_platform_key_is_invalid(self):
        user_with_credits = stubs.domain.user(
            open_ai_key = None,
                    )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("invalid")
            token = resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_uses_platform_key_when_sponsored_user_has_credits(self):
        user_no_key = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsor_with_credits = stubs.domain.user(
            id = UUID(int = 2),
            open_ai_key = None,
            credit_balance = 50.0,
        )
        sponsorship = stubs.domain.sponsorship(sponsor_id = sponsor_with_credits.id, receiver_id = user_no_key.id)
        self.mock_di.invoker = user_no_key
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = sponsor_with_credits

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
        self.assertTrue(token.uses_credits)

    def test_get_access_token_returns_none_when_credit_balance_is_zero(self):
        user_zero_credits = stubs.domain.user(
            open_ai_key = None,
            credit_balance = 0.0,
        )
        self.mock_di.invoker = user_zero_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_returns_none_when_credit_balance_is_negative(self):
        user_negative_credits = stubs.domain.user(
            open_ai_key = None,
            credit_balance = -10.0,
        )
        self.mock_di.invoker = user_negative_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_payer_id_is_invoker_when_using_platform_key(self):
        user_with_credits = stubs.domain.user(
            open_ai_key = None,
                    )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertEqual(token.payer_id, user_with_credits.id)
        self.assertTrue(token.uses_credits)

    def test_get_access_token_payer_id_is_sponsor_when_sponsor_uses_platform_key(self):
        user_no_key = stubs.domain.user(id = UUID(int = 1), open_ai_key = None, credit_balance = 0.0)
        sponsor_with_credits = stubs.domain.user(
            id = UUID(int = 2),
            open_ai_key = None,
            credit_balance = 50.0,
        )
        sponsorship = stubs.domain.sponsorship(sponsor_id = sponsor_with_credits.id, receiver_id = user_no_key.id)
        self.mock_di.invoker = user_no_key
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_user_repo.get.return_value = sponsor_with_credits

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(OPEN_AI)

        assert token is not None
        self.assertEqual(token.payer_id, sponsor_with_credits.id)
        self.assertTrue(token.uses_credits)

    def test_platform_key_anthropic_with_credits(self):
        user_with_credits = stubs.domain.user(
            anthropic_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_anthropic_key = SecretStr("platform-anthropic-key")
            token = resolver.get_access_token(ANTHROPIC)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-anthropic-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_google_ai_with_credits(self):
        user_with_credits = stubs.domain.user(
            google_ai_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_google_ai_key = SecretStr("platform-google-key")
            token = resolver.get_access_token(GOOGLE_AI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-google-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_perplexity_with_credits(self):
        user_with_credits = stubs.domain.user(
            perplexity_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_perplexity_key = SecretStr("platform-perplexity-key")
            token = resolver.get_access_token(PERPLEXITY)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-perplexity-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_replicate_with_credits(self):
        user_with_credits = stubs.domain.user(
            replicate_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_replicate_key = SecretStr("platform-replicate-key")
            token = resolver.get_access_token(REPLICATE)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-replicate-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_rapid_api_with_credits(self):
        user_with_credits = stubs.domain.user(
            rapid_api_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_rapid_api_key = SecretStr("platform-rapid-api-key")
            token = resolver.get_access_token(RAPID_API)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-rapid-api-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_coinmarketcap_with_credits(self):
        user_with_credits = stubs.domain.user(
            coinmarketcap_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_coinmarketcap_key = SecretStr("platform-coinmarketcap-key")
            token = resolver.get_access_token(COINMARKETCAP)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-coinmarketcap-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_twelve_data_with_credits(self):
        user_with_credits = stubs.domain.user(
            twelve_data_api_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_twelve_data_api_key = SecretStr("platform-twelve-data-key")
            token = resolver.get_access_token(TWELVE_DATA)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-twelve-data-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_x_api_with_credits(self):
        user_with_credits = stubs.domain.user(
            x_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_x_key = SecretStr("platform-x-key")
            token = resolver.get_access_token(X)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-x-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_x_ai_with_credits(self):
        user_with_credits = stubs.domain.user(
            x_ai_key = None,
            credit_balance = 50.0,
        )
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_x_ai_key = SecretStr("platform-x-ai-key")
            token = resolver.get_access_token(XAI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-x-ai-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)
