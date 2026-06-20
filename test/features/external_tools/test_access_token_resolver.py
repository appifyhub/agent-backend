import unittest
from dataclasses import replace
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import UUID

from pydantic import SecretStr

from db.crud.user import UserCRUD
from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.external_tools.access_token_resolver import AccessTokenResolver, ResolvedToken, TokenResolutionError
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from features.external_tools.external_tool_provider_library import (
    ANTHROPIC,
    COINMARKETCAP,
    GOOGLE_AI,
    OPEN_AI,
    PERPLEXITY,
    RAPID_API,
    REPLICATE,
    XAI,
    X,
)
from features.sponsorships.sponsorship import Sponsorship
from features.sponsorships.sponsorship_repo import SponsorshipRepository


class AccessTokenResolverTest(unittest.TestCase):

    invoker_user: User
    sponsor_user: User
    sponsorship: Sponsorship
    mock_user_dao: UserCRUD
    mock_sponsorship_repo: SponsorshipRepository
    mock_di: DI
    openai_provider: ExternalToolProvider
    anthropic_provider: ExternalToolProvider
    openai_tool: ExternalTool

    def setUp(self):
        self.invoker_user = User(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_user",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("invoker_openai_key"),
            anthropic_key = SecretStr("invoker_anthropic_key"),
            google_ai_key = SecretStr("invoker_google_ai_key"),
            perplexity_key = SecretStr("invoker_perplexity_key"),
            replicate_key = SecretStr("invoker_replicate_key"),
            rapid_api_key = SecretStr("invoker_rapid_api_key"),
            coinmarketcap_key = SecretStr("invoker_coinmarketcap_key"),
            x_key = SecretStr("invoker_x_key"),
            x_ai_key = SecretStr("invoker_x_ai_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.sponsor_user = User(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_user",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
            open_ai_key = SecretStr("sponsor_openai_key"),
            anthropic_key = SecretStr("sponsor_anthropic_key"),
            google_ai_key = SecretStr("sponsor_google_ai_key"),
            perplexity_key = SecretStr("sponsor_perplexity_key"),
            replicate_key = SecretStr("sponsor_replicate_key"),
            rapid_api_key = SecretStr("sponsor_rapid_api_key"),
            coinmarketcap_key = SecretStr("sponsor_coinmarketcap_key"),
            x_key = SecretStr("sponsor_x_key"),
            x_ai_key = SecretStr("sponsor_x_ai_key"),
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )
        self.sponsorship = Sponsorship(
            sponsor_id = self.sponsor_user.id,
            receiver_id = self.invoker_user.id,
            sponsored_at = datetime.now(),
            accepted_at = datetime.now(),
        )

        self.mock_user_dao = Mock(spec = UserCRUD)
        self.mock_sponsorship_repo = Mock(spec = SponsorshipRepository)
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_crud = self.mock_user_dao
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo
        # noinspection PyPropertyAccess
        self.mock_di.invoker = self.invoker_user

        self.openai_provider = OPEN_AI
        self.anthropic_provider = ANTHROPIC
        self.openai_tool = ExternalTool(
            id = "test-gpt-4",
            name = "Test GPT-4",
            provider = self.openai_provider,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )

    def test_init_with_user_object_success(self):
        resolver = AccessTokenResolver(self.mock_di)

        # Should not raise an exception
        self.assertIsNotNone(resolver)
        # noinspection PyUnresolvedReferences
        self.mock_user_dao.get.assert_not_called()

    def test_get_access_token_success_user_has_direct_token(self):
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.open_ai_key.get_secret_value())
        self.assertFalse(token.uses_credits)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_not_called()

    def test_get_access_token_success_user_no_token_has_sponsorship(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        sponsor_user_db = UserDB(**self.sponsor_user.model_dump())
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [self.sponsorship]
        self.mock_user_dao.get.return_value = sponsor_user_db

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.sponsor_user.open_ai_key.get_secret_value())
        self.assertFalse(token.uses_credits)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        # noinspection PyUnresolvedReferences
        self.mock_user_dao.get.assert_called_once_with(self.sponsorship.sponsor_id)

    def test_get_access_token_failure_pending_sponsorship_not_accepted(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        pending_sponsorship = replace(self.sponsorship, accepted_at = None)
        self.mock_di.invoker = user_without_token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [pending_sponsorship]

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        self.assertIsNone(token)
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        self.mock_user_dao.get.assert_not_called()

    def test_get_access_token_failure_user_no_token_no_sponsorship(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        assert token is None
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)

    def test_get_access_token_failure_user_no_token_sponsor_not_found(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [self.sponsorship]
        self.mock_user_dao.get.return_value = None

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        assert token is None
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.get_all_by_receiver.assert_called_once_with(user_without_token.id, limit = 1)
        # noinspection PyUnresolvedReferences
        self.mock_user_dao.get.assert_called_once_with(self.sponsorship.sponsor_id)

    def test_get_access_token_failure_user_no_token_sponsor_no_token(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        sponsor_without_token = self.sponsor_user.model_copy(update = {"open_ai_key": None})
        sponsor_user_db = UserDB(**sponsor_without_token.model_dump())
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [self.sponsorship]
        self.mock_user_dao.get.return_value = sponsor_user_db

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(self.openai_provider)

        assert token is None

    def test_get_access_token_failure_unsupported_provider(self):
        # Set up mock to return empty list to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        # Create a truly unsupported provider
        unsupported_provider = ExternalToolProvider(
            id = "unsupported",
            name = "Unsupported Provider",
            token_management_url = "https://example.com",
            token_format = "test-token",
            tools = ["test-tool"],
        )

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(unsupported_provider)

        self.assertIsNone(token)

    def test_get_access_token_for_tool_success(self):
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token_for_tool(self.openai_tool)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.open_ai_key.get_secret_value())

    def test_require_access_token_success(self):
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.require_access_token(self.openai_provider)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.open_ai_key.get_secret_value())

    def test_require_access_token_failure_raises_exception(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)

        with self.assertRaises(TokenResolutionError) as context:
            resolver.require_access_token(self.openai_provider)

        self.assertIn(f"Unable to resolve an access token for '{self.openai_provider.name}'", str(context.exception))

    def test_require_access_token_for_tool_success(self):
        # Mock to avoid sponsorship lookup since user has direct token
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.require_access_token_for_tool(self.openai_tool)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.open_ai_key.get_secret_value())

    def test_require_access_token_for_tool_failure_raises_exception(self):
        user_without_token = self.invoker_user.model_copy(update = {"open_ai_key": None})
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        # noinspection PyPropertyAccess
        self.mock_di.invoker = user_without_token

        resolver = AccessTokenResolver(self.mock_di)

        with self.assertRaises(TokenResolutionError):
            resolver.require_access_token_for_tool(self.openai_tool)

    def test_get_access_token_anthropic_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(ANTHROPIC)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.anthropic_key.get_secret_value())

    def test_get_access_token_perplexity_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(PERPLEXITY)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.perplexity_key.get_secret_value())

    def test_get_access_token_replicate_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(REPLICATE)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.replicate_key.get_secret_value())

    def test_get_access_token_rapid_api_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(RAPID_API)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.rapid_api_key.get_secret_value())

    def test_get_access_token_coinmarketcap_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(COINMARKETCAP)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.coinmarketcap_key.get_secret_value())

    def test_get_access_token_x_api_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(X)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.x_key.get_secret_value())

    def test_get_access_token_x_ai_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(XAI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.x_ai_key.get_secret_value())

    def test_get_access_token_google_ai_success_user_has_direct_token(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        token = resolver.get_access_token(GOOGLE_AI)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), self.invoker_user.google_ai_key.get_secret_value())

    def test_get_access_token_uses_platform_key_when_user_has_credits(self):
        user_with_credits = self.invoker_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 100.0,
        })
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key.get_secret_value.return_value = "platform-openai-key"
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
        self.assertTrue(token.uses_credits)

    def test_get_access_token_returns_none_when_platform_key_is_invalid(self):
        user_with_credits = self.invoker_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 100.0,
        })
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("invalid")
            token = resolver.get_access_token(self.openai_provider)

        self.assertIsNone(token)

    def test_get_access_token_uses_platform_key_when_sponsored_user_has_credits(self):
        user_no_key = self.invoker_user.model_copy(update = {"open_ai_key": None})
        sponsor_with_credits = self.sponsor_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 50.0,
        })
        sponsor_user_db = UserDB(**sponsor_with_credits.model_dump())
        self.mock_di.invoker = user_no_key
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [self.sponsorship]
        self.mock_user_dao.get.return_value = sponsor_user_db

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertIsInstance(token, ResolvedToken)
        self.assertEqual(token.token.get_secret_value(), "platform-openai-key")
        self.assertTrue(token.uses_credits)

    def test_get_access_token_returns_none_when_credit_balance_is_zero(self):
        user_zero_credits = self.invoker_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 0.0,
        })
        self.mock_di.invoker = user_zero_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        self.assertIsNone(token)

    def test_get_access_token_returns_none_when_credit_balance_is_negative(self):
        user_negative_credits = self.invoker_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": -10.0,
        })
        self.mock_di.invoker = user_negative_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        self.assertIsNone(token)

    def test_get_access_token_payer_id_is_invoker_when_using_platform_key(self):
        user_with_credits = self.invoker_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 100.0,
        })
        self.mock_di.invoker = user_with_credits
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertEqual(token.payer_id, user_with_credits.id)
        self.assertTrue(token.uses_credits)

    def test_get_access_token_payer_id_is_sponsor_when_sponsor_uses_platform_key(self):
        user_no_key = self.invoker_user.model_copy(update = {"open_ai_key": None})
        sponsor_with_credits = self.sponsor_user.model_copy(update = {
            "open_ai_key": None,
            "credit_balance": 50.0,
        })
        sponsor_user_db = UserDB(**sponsor_with_credits.model_dump())
        self.mock_di.invoker = user_no_key
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [self.sponsorship]
        self.mock_user_dao.get.return_value = sponsor_user_db

        resolver = AccessTokenResolver(self.mock_di)

        with patch("features.external_tools.access_token_resolver.config") as mock_config:
            mock_config.platform_open_ai_key = SecretStr("platform-openai-key")
            token = resolver.get_access_token(self.openai_provider)

        assert token is not None
        self.assertEqual(token.payer_id, sponsor_with_credits.id)
        self.assertTrue(token.uses_credits)

    def test_platform_key_anthropic_with_credits(self):
        user_with_credits = self.invoker_user.model_copy(update = {
            "anthropic_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "google_ai_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "perplexity_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "replicate_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "rapid_api_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "coinmarketcap_key": None,
            "credit_balance": 50.0,
        })
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

    def test_platform_key_x_api_with_credits(self):
        user_with_credits = self.invoker_user.model_copy(update = {
            "x_key": None,
            "credit_balance": 50.0,
        })
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
        user_with_credits = self.invoker_user.model_copy(update = {
            "x_ai_key": None,
            "credit_balance": 50.0,
        })
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
