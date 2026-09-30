from unittest import TestCase
from uuid import UUID

import stubs
from pydantic import SecretStr
from util.di_utils import di_for_tests

from di.di import DI
from features.external_tools.access_token_resolver import AccessTokenResolver, TokenResolutionError
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
from util.config import config


class AccessTokenResolverTest(TestCase):

    di: DI
    resolver: AccessTokenResolver

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.resolver = self.di.access_token_resolver

    def test_get_access_token_success_user_has_direct_token(self):
        user = self.di.user_repo.save(stubs.domain.user())
        sponsor = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
            open_ai_key = SecretStr("sponsor-openai-key"),
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(sponsor_id = sponsor.id, receiver_id = user.id))
        self.di.inject_invoker(user)

        token = self.resolver.get_access_token(OPEN_AI)

        self.assertEqual(token, stubs.domain.resolved_token(token = user.open_ai_key, payer_id = user.id))

    def test_get_access_token_success_user_no_token_has_sponsorship(self):
        user_without_token = self.di.user_repo.save(stubs.domain.user(open_ai_key = None, credit_balance = 0.0))
        sponsor_user = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = user_without_token.id,
        ))
        self.di.inject_invoker(user_without_token)

        token = self.resolver.get_access_token(OPEN_AI)

        self.assertEqual(token, stubs.domain.resolved_token(token = sponsor_user.open_ai_key, payer_id = sponsor_user.id))

    def test_get_access_token_failure_pending_sponsorship_not_accepted(self):
        user_without_token = self.di.user_repo.save(stubs.domain.user(open_ai_key = None, credit_balance = 0.0))
        sponsor = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = user_without_token.id,
            accepted_at = None,
        ))
        self.di.inject_invoker(user_without_token)

        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_failure_user_no_token_no_sponsorship(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.di.inject_invoker(user_without_token)

        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_failure_user_no_token_sponsor_no_token(self):
        user_without_token = self.di.user_repo.save(stubs.domain.user(open_ai_key = None, credit_balance = 0.0))
        sponsor_without_token = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
            open_ai_key = None,
            credit_balance = 0.0,
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = sponsor_without_token.id,
            receiver_id = user_without_token.id,
        ))
        self.di.inject_invoker(user_without_token)

        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_failure_unsupported_provider(self):
        self.di.inject_invoker(stubs.domain.user())

        unsupported_provider = stubs.domain.external_tool_provider(id = "unsupported")

        token = self.resolver.get_access_token(unsupported_provider)

        self.assertIsNone(token)

    def test_get_access_token_for_tool_success(self):
        self.di.inject_invoker(stubs.domain.user())

        tool = GPT_5_6_TERRA

        token = self.resolver.get_access_token_for_tool(tool)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_success(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.require_access_token(OPEN_AI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_failure_raises_exception(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.di.inject_invoker(user_without_token)

        with self.assertRaises(TokenResolutionError) as context:
            self.resolver.require_access_token(OPEN_AI)

        self.assertIn(f"Unable to resolve an access token for '{OPEN_AI.name}'", str(context.exception))

    def test_require_access_token_for_tool_success(self):
        self.di.inject_invoker(stubs.domain.user())

        tool = GPT_5_6_TERRA

        token = self.resolver.require_access_token_for_tool(tool)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.open_ai_key.get_secret_value())

    def test_require_access_token_for_tool_failure_raises_exception(self):
        user_without_token = stubs.domain.user(open_ai_key = None, credit_balance = 0.0)
        self.di.inject_invoker(user_without_token)

        tool = GPT_5_6_TERRA

        with self.assertRaises(TokenResolutionError):
            self.resolver.require_access_token_for_tool(tool)

    def test_get_access_token_anthropic_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(ANTHROPIC)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.anthropic_key.get_secret_value())

    def test_get_access_token_perplexity_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(PERPLEXITY)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.perplexity_key.get_secret_value())

    def test_get_access_token_replicate_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(REPLICATE)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.replicate_key.get_secret_value())

    def test_get_access_token_rapid_api_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(RAPID_API)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.rapid_api_key.get_secret_value())

    def test_get_access_token_coinmarketcap_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(COINMARKETCAP)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.coinmarketcap_key.get_secret_value())

    def test_get_access_token_twelve_data_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(TWELVE_DATA)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.twelve_data_api_key.get_secret_value())
        self.assertFalse(token.uses_credits)

    def test_get_access_token_twelve_data_success_sponsor_has_token(self):
        user_without_token = self.di.user_repo.save(stubs.domain.user(twelve_data_api_key = None, credit_balance = 0.0))
        sponsor_user = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = user_without_token.id,
        ))
        self.di.inject_invoker(user_without_token)

        token = self.resolver.get_access_token(TWELVE_DATA)

        self.assertEqual(token, stubs.domain.resolved_token(token = sponsor_user.twelve_data_api_key, payer_id = sponsor_user.id))

    def test_get_access_token_x_api_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(X)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.x_key.get_secret_value())

    def test_get_access_token_x_ai_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(XAI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.x_ai_key.get_secret_value())

    def test_get_access_token_google_ai_success_user_has_direct_token(self):
        self.di.inject_invoker(stubs.domain.user())

        token = self.resolver.get_access_token(GOOGLE_AI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), self.di.invoker.google_ai_key.get_secret_value())

    def test_get_access_token_uses_platform_key_when_user_has_credits(self):
        user_with_credits = stubs.domain.user(
            open_ai_key = None,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("platform-openai-key")
        token = self.resolver.get_access_token(OPEN_AI)

        self.assertEqual(token, stubs.domain.resolved_token(
            token = SecretStr("platform-openai-key"),
            payer_id = user_with_credits.id,
            uses_credits = True,
        ))

    def test_get_access_token_system_agents_use_platform_key_without_credits(self):
        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("platform-openai-key")

        for agent in SYSTEM_AGENTS:
            with self.subTest(agent_id = agent.id):
                system_agent = stubs.domain.user(
                    id = agent.id,
                    open_ai_key = SecretStr("stale-agent-key"),
                    credit_balance = 0.0,
                )
                self.di.inject_invoker(system_agent)

                token = self.resolver.get_access_token(OPEN_AI)

                assert token is not None
                self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
                self.assertEqual(token.payer_id, agent.id)
                self.assertFalse(token.uses_credits)

    def test_get_access_token_returns_none_when_platform_key_is_invalid(self):
        user_with_credits = stubs.domain.user(
            open_ai_key = None,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("invalid")
        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_uses_platform_key_when_sponsored_user_has_credits(self):
        user_no_key = self.di.user_repo.save(stubs.domain.user(open_ai_key = None, credit_balance = 0.0))
        sponsor_with_credits = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSOR-KEY",
            open_ai_key = None,
            credit_balance = 50.0,
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = sponsor_with_credits.id,
            receiver_id = user_no_key.id,
        ))
        self.di.inject_invoker(user_no_key)

        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("platform-openai-key")
        token = self.resolver.get_access_token(OPEN_AI)

        self.assertEqual(token, stubs.domain.resolved_token(
            token = SecretStr("platform-openai-key"),
            payer_id = sponsor_with_credits.id,
            uses_credits = True,
        ))

    def test_get_access_token_returns_none_when_credit_balance_is_zero(self):
        user_zero_credits = stubs.domain.user(
            open_ai_key = None,
            credit_balance = 0.0,
        )
        self.di.inject_invoker(user_zero_credits)

        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("platform-openai-key")
        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_get_access_token_returns_none_when_credit_balance_is_negative(self):
        user_negative_credits = stubs.domain.user(
            open_ai_key = None,
            credit_balance = -10.0,
        )
        self.di.inject_invoker(user_negative_credits)

        self.addCleanup(setattr, config, "platform_open_ai_key", config.platform_open_ai_key)
        config.platform_open_ai_key = SecretStr("platform-openai-key")
        token = self.resolver.get_access_token(OPEN_AI)

        self.assertIsNone(token)

    def test_platform_key_anthropic_with_credits(self):
        user_with_credits = stubs.domain.user(
            anthropic_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_anthropic_key", config.platform_anthropic_key)
        config.platform_anthropic_key = SecretStr("platform-anthropic-key")
        token = self.resolver.get_access_token(ANTHROPIC)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-anthropic-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_google_ai_with_credits(self):
        user_with_credits = stubs.domain.user(
            google_ai_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_google_ai_key", config.platform_google_ai_key)
        config.platform_google_ai_key = SecretStr("platform-google-key")
        token = self.resolver.get_access_token(GOOGLE_AI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-google-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_perplexity_with_credits(self):
        user_with_credits = stubs.domain.user(
            perplexity_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_perplexity_key", config.platform_perplexity_key)
        config.platform_perplexity_key = SecretStr("platform-perplexity-key")
        token = self.resolver.get_access_token(PERPLEXITY)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-perplexity-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_replicate_with_credits(self):
        user_with_credits = stubs.domain.user(
            replicate_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_replicate_key", config.platform_replicate_key)
        config.platform_replicate_key = SecretStr("platform-replicate-key")
        token = self.resolver.get_access_token(REPLICATE)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-replicate-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_rapid_api_with_credits(self):
        user_with_credits = stubs.domain.user(
            rapid_api_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_rapid_api_key", config.platform_rapid_api_key)
        config.platform_rapid_api_key = SecretStr("platform-rapid-api-key")
        token = self.resolver.get_access_token(RAPID_API)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-rapid-api-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_coinmarketcap_with_credits(self):
        user_with_credits = stubs.domain.user(
            coinmarketcap_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_coinmarketcap_key", config.platform_coinmarketcap_key)
        config.platform_coinmarketcap_key = SecretStr("platform-coinmarketcap-key")
        token = self.resolver.get_access_token(COINMARKETCAP)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-coinmarketcap-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_twelve_data_with_credits(self):
        user_with_credits = stubs.domain.user(
            twelve_data_api_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_twelve_data_api_key", config.platform_twelve_data_api_key)
        config.platform_twelve_data_api_key = SecretStr("platform-twelve-data-key")
        token = self.resolver.get_access_token(TWELVE_DATA)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-twelve-data-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_x_api_with_credits(self):
        user_with_credits = stubs.domain.user(
            x_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_x_key", config.platform_x_key)
        config.platform_x_key = SecretStr("platform-x-key")
        token = self.resolver.get_access_token(X)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-x-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)

    def test_platform_key_x_ai_with_credits(self):
        user_with_credits = stubs.domain.user(
            x_ai_key = None,
            credit_balance = 50.0,
        )
        self.di.inject_invoker(user_with_credits)

        self.addCleanup(setattr, config, "platform_x_ai_key", config.platform_x_ai_key)
        config.platform_x_ai_key = SecretStr("platform-x-ai-key")
        token = self.resolver.get_access_token(XAI)

        assert token is not None
        self.assertEqual(token.token.get_secret_value(), "platform-x-ai-key")
        self.assertTrue(token.uses_credits)
        self.assertEqual(token.payer_id, user_with_credits.id)
