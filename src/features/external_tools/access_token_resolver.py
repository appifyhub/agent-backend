from dataclasses import dataclass
from uuid import UUID

from pydantic import SecretStr

from di.di import DI
from features.external_tools.external_tool import ExternalTool, ExternalToolProvider
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
from features.users.user import User
from util import log
from util.config import config
from util.error_codes import TOKEN_NOT_FOUND
from util.errors import NotFoundError


@dataclass(frozen = True)
class ResolvedToken:
    token: SecretStr
    payer_id: UUID
    uses_credits: bool


class TokenResolutionError(NotFoundError):

    def __init__(self, tool_provider: ExternalToolProvider, tool: ExternalTool | None = None):
        message = f"Unable to resolve an access token for '{tool_provider.name}'"
        if tool:
            message += f" - '{tool.name}'"
        message += ". Check your profile settings page."
        super().__init__(message, TOKEN_NOT_FOUND)


class AccessTokenResolver:

    __di: DI
    __sponsor_cache: dict[str, User | None]

    def __init__(self, di: DI):
        self.__di = di
        self.__sponsor_cache = {}

    def require_access_token_for_tool(self, tool: ExternalTool) -> ResolvedToken:
        result = self.get_access_token_for_tool(tool)
        if result is None:
            raise TokenResolutionError(tool.provider, tool)
        return result

    def require_access_token(self, provider: ExternalToolProvider) -> ResolvedToken:
        result = self.get_access_token(provider)
        if result is None:
            raise TokenResolutionError(provider)
        return result

    def get_access_token_for_tool(self, tool: ExternalTool) -> ResolvedToken | None:
        log.t(f"Resolving access token for tool '{tool.id}'")
        return self.get_access_token(tool.provider)

    def get_access_token(self, provider: ExternalToolProvider) -> ResolvedToken | None:
        log.t(f"Resolving access token for provider '{provider.id}'")
        invoker = self.__di.invoker

        # check if invoker has a direct token
        user_token = self.__get_user_token_for_provider(invoker, provider)
        if user_token:
            log.t(f"Found direct token for provider '{provider.id}'")
            return ResolvedToken(token = user_token, payer_id = invoker.id, uses_credits = False)
        log.t("No direct token found for invoker user")

        # check if invoker has a sponsorship (with caching), and
        # check sponsor's token for this provider (if sponsored)
        sponsor_user = self.__get_sponsor_user(invoker.id.hex)
        if sponsor_user:
            sponsor_token = self.__get_user_token_for_provider(sponsor_user, provider)
            if sponsor_token:
                log.t(f"Found sponsor token for provider '{provider.id}'")
                return ResolvedToken(token = sponsor_token, payer_id = sponsor_user.id, uses_credits = False)
        log.t("No sponsor token found for invoker user")

        # fall back to platform keys if billing user has credits
        billing_user = sponsor_user if sponsor_user is not None else invoker
        if billing_user.credit_balance > 0:
            platform_token = self.__get_platform_token_for_provider(provider)
            if platform_token:
                log.t(f"Using platform token for provider '{provider.id}' (billing user: {billing_user.id})")
                return ResolvedToken(token = platform_token, payer_id = billing_user.id, uses_credits = True)

        log.t(f"No token found for provider '{provider.id}', no credits available either")
        return None

    def __get_sponsor_user(self, user_id_hex: str) -> User | None:
        # check cache first
        if user_id_hex in self.__sponsor_cache:
            log.t(f"Using cached sponsor info for user '{user_id_hex}'")
            return self.__sponsor_cache[user_id_hex]

        # cache miss - fetch from database
        log.t(f"Fetching sponsor info for user '{user_id_hex}' from database")
        user_id = UUID(hex = user_id_hex)
        sponsorships = self.__di.sponsorship_repo.get_all_by_receiver(user_id, limit = 1)
        if not sponsorships:
            log.t(f"User '{user_id_hex}' has no sponsorships")
            self.__sponsor_cache[user_id_hex] = None
            return None

        # get sponsor user
        log.t("Checking sponsorships for user now")
        sponsorship = sponsorships[0]
        if sponsorship.accepted_at is None:
            log.t(f"User '{user_id_hex}' has no accepted sponsorships")
            self.__sponsor_cache[user_id_hex] = None
            return None
        sponsor_user = self.__di.user_repo.get(sponsorship.sponsor_id)

        if not sponsor_user:
            log.t(f"Sponsor '{sponsorship.sponsor_id.hex}' not found")
            self.__sponsor_cache[user_id_hex] = None
            return None

        self.__sponsor_cache[user_id_hex] = sponsor_user
        log.t(f"Cached sponsor '{sponsor_user.id.hex}' for user '{user_id_hex}'")
        return sponsor_user

    def __get_platform_token_for_provider(self, provider: ExternalToolProvider) -> SecretStr | None:
        token: SecretStr | None = None
        match provider.id:
            case OPEN_AI.id:
                token = config.platform_open_ai_key
            case ANTHROPIC.id:
                token = config.platform_anthropic_key
            case GOOGLE_AI.id:
                token = config.platform_google_ai_key
            case PERPLEXITY.id:
                token = config.platform_perplexity_key
            case REPLICATE.id:
                token = config.platform_replicate_key
            case RAPID_API.id:
                token = config.platform_rapid_api_key
            case COINMARKETCAP.id:
                token = config.platform_coinmarketcap_key
            case X.id:
                token = config.platform_x_key
            case XAI.id:
                token = config.platform_x_ai_key
        if token is None or token.get_secret_value() == "invalid":
            return None
        return token

    def __get_user_token_for_provider(self, user: User, provider: ExternalToolProvider) -> SecretStr | None:
        match provider.id:
            case OPEN_AI.id:
                return user.open_ai_key
            case ANTHROPIC.id:
                return user.anthropic_key
            case PERPLEXITY.id:
                return user.perplexity_key
            case REPLICATE.id:
                return user.replicate_key
            case RAPID_API.id:
                return user.rapid_api_key
            case COINMARKETCAP.id:
                return user.coinmarketcap_key
            case GOOGLE_AI.id:
                return user.google_ai_key
            case X.id:
                return user.x_key
            case XAI.id:
                return user.x_ai_key
        log.t(f"Unknown provider '{provider.id}'")
        return None
