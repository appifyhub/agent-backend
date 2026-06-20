from dataclasses import replace
from datetime import datetime, timedelta
from typing import Annotated, Literal, TypeAlias, get_args
from uuid import UUID

from api import auth
from api.mapper.chat_settings_mapper import domain_to_api as chat_to_api
from api.mapper.user_mapper import api_to_domain, domain_to_api
from api.model.chat_config_payload import ChatConfigPayload
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.chat_settings_response import ChatSettingsResponse
from api.model.external_tools_response import ExternalToolProviderResponse, ExternalToolResponse, ExternalToolsResponse
from api.model.products_response import ProductsResponse
from api.model.settings_link_response import SettingsLinkResponse
from api.model.user_chat_config_payload import UserChatConfigPayload
from api.model.user_settings_payload import UserSettingsPayload
from api.model.user_settings_response import UserSettingsResponse
from db.model.chat_config import ChatConfigDB
from db.schema.user import User
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership
from features.external_tools.external_tool_library import ALL_EXTERNAL_TOOLS
from features.external_tools.external_tool_provider_library import ALL_PROVIDERS
from features.external_tools.intelligence_presets import get_all_presets
from features.integrations.integrations import is_own_chat, resolve_agent_user, resolve_external_handle, resolve_external_id
from util import log
from util.config import config
from util.error_codes import (
    EMPTY_CHAT_SETTINGS_PAYLOAD,
    INVALID_LANGUAGE_SETTINGS,
    INVALID_MEDIA_MODE,
    INVALID_RELEASE_NOTIFICATIONS,
    INVALID_REPLY_CHANCE,
    INVALID_SETTINGS_TYPE,
    INVALID_TOOL_CHOICE,
    MISSING_CHAT_CONTEXT,
    NO_PRIVATE_CHAT,
    POLICY_ACCEPTANCE_REVOCATION_FORBIDDEN,
)
from util.errors import AuthorizationError, ConfigurationError, ValidationError

SettingsType: TypeAlias = Annotated[str, Literal["user", "chat", "intelligence"]]
InvokerType: TypeAlias = Annotated[str, Literal["creator", "administrator"]]
DEF_SETTINGS_TYPE: SettingsType = "intelligence"
SETTINGS_TOKEN_VAR: str = "token"


class SettingsController:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def __validate_settings_type(self, settings_type: str) -> SettingsType:
        log.d("Validating settings type")
        literal_type = get_args(SettingsType)[1]
        if settings_type not in get_args(literal_type):
            raise ValidationError(f"Invalid settings type '{settings_type}'", INVALID_SETTINGS_TYPE)
        return settings_type

    def create_settings_link(
        self,
        raw_settings_type: str | None = None,
        chat_type: ChatConfigDB.ChatType | None = None,
    ) -> SettingsLinkResponse:
        chat_type = chat_type or self.__di.invoker_chat_type
        if not chat_type:
            raise ConfigurationError("Chat type not provided and invoker_chat is not available", MISSING_CHAT_CONTEXT)
        external_id = resolve_external_id(self.__di.invoker, chat_type)
        if not external_id:
            raise AuthorizationError("User never sent a private message, cannot create a settings link", NO_PRIVATE_CHAT)

        settings_type: SettingsType
        lang_iso_code: str
        resource_id: str
        if self.__di.invoker_chat:
            # chat context has additional chat-specific properties we can use
            settings_type = self.__validate_settings_type(raw_settings_type) if raw_settings_type else DEF_SETTINGS_TYPE
            chat_config = self.__di.invoker_chat
            if settings_type == "chat":
                # any member can access their per-chat settings where admin rights are not required
                self.__di.chat_membership_service.sync(self.__di.invoker, chat_config)
            resource_id = self.__di.invoker.id.hex if settings_type in ("user", "intelligence") else chat_config.chat_id.hex
            lang_iso_code = chat_config.language_iso_code or "en"
        else:
            # API context only supports user settings, we default to the basics
            settings_type = DEF_SETTINGS_TYPE
            resource_id = self.__di.invoker.id.hex
            lang_iso_code = config.main_language_iso_code

        jwt_token = self.__create_jwt_token(chat_type)
        is_sponsored = self.__is_sponsored(self.__di.invoker.id)
        url_type = "user" if settings_type in ("user", "intelligence") else settings_type
        if is_sponsored and settings_type in ("user", "intelligence"):
            page = "sponsorships"
        elif settings_type == "intelligence":
            page = "intelligence"
        else:
            page = "settings"
        settings_url_base = f"{config.backoffice_url_base}/{lang_iso_code}/{url_type}/{resource_id}/{page}"
        long_url = f"{settings_url_base}?{SETTINGS_TOKEN_VAR}={jwt_token}"

        valid_until = datetime.now() + timedelta(minutes = config.jwt_expires_in_minutes * 10)
        shortener = self.__di.url_shortener(long_url, valid_until = valid_until)
        return SettingsLinkResponse(settings_link = shortener.execute())

    def create_help_link(self, chat_type: ChatConfigDB.ChatType | None = None) -> str:
        chat_type = chat_type or self.__di.invoker_chat_type
        if not chat_type:
            raise ConfigurationError("Chat type not provided and invoker_chat is not available", MISSING_CHAT_CONTEXT)
        external_id = resolve_external_id(self.__di.invoker, chat_type)
        if not external_id:
            raise AuthorizationError("User never sent a private message, cannot create settings link", NO_PRIVATE_CHAT)

        lang_iso_code: str
        if self.__di.invoker_chat:
            chat_config = self.__di.invoker_chat
            lang_iso_code = chat_config.language_iso_code or config.main_language_iso_code
        else:
            lang_iso_code = config.main_language_iso_code

        jwt_token = self.__create_jwt_token(chat_type)
        settings_url_base = f"{config.backoffice_url_base}/{lang_iso_code}/features"
        long_url = f"{settings_url_base}?{SETTINGS_TOKEN_VAR}={jwt_token}"

        valid_until = datetime.now() + timedelta(minutes = config.jwt_expires_in_minutes * 10)
        shortener = self.__di.url_shortener(long_url, valid_until = valid_until)
        return shortener.execute()

    def fetch_external_tools(self, user_id_hex: str) -> ExternalToolsResponse:
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        scoped_di = self.__di.clone(invoker_id = user.id.hex)

        # build the provider list first because we will need it to sort the tools (and check access from cache)
        providers_response: list[ExternalToolProviderResponse] = []
        provider_is_configured_cache: dict[str, bool] = {}
        provider_sort_order: dict[str, int] = {}
        for i, provider in enumerate(ALL_PROVIDERS):
            is_configured = scoped_di.access_token_resolver.get_access_token(provider) is not None
            providers_response.append(ExternalToolProviderResponse(provider, is_configured))
            provider_is_configured_cache[provider.id] = is_configured
            provider_sort_order[provider.id] = i

        # now we build the tool list using cached information
        tools_response: list[ExternalToolResponse] = []
        for tool in ALL_EXTERNAL_TOOLS:
            is_configured = provider_is_configured_cache[tool.provider.id]
            tools_response.append(ExternalToolResponse(tool, is_configured))

        # and finally, we sort the tools by [1] provider order and [2] tool name
        tools_response.sort(key = lambda t: (provider_sort_order[t.definition.provider.id], t.definition.name))

        return ExternalToolsResponse(tools_response, providers_response, get_all_presets())

    def fetch_products(self, user_id_hex: str) -> ProductsResponse:
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        products = [
            replace(product, url = f"{product.url}?user_id={user.id.hex}")
            for product in config.products.values()
        ]
        return ProductsResponse(products)

    def fetch_user_settings(self, user_id_hex: str) -> UserSettingsResponse:
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        return domain_to_api(user, self.__is_sponsored(user.id))

    def fetch_all_chat_settings(self) -> list[ChatSettingsResponse]:
        log.d("Fetching all chats for invoker")

        memberships = self.__di.authorization_service.update_all_chat_authorizations(self.__di.invoker)
        if not memberships:
            log.d("  No memberships found")
            return []

        results: list[tuple[ChatConfig, ChatMembership]] = []
        for membership in memberships:
            chat_config = self.__di.chat_config_repo.get(membership.chat_id)
            if not chat_config:
                log.t(f"  Skipping orphan membership for chat '{membership.chat_id}' (chat config missing)")
                continue
            results.append((chat_config, membership))

        # sort: private/own first, then by chat type, then by title
        results.sort(
            key = lambda pair: (
                not pair[0].is_private,
                not pair[1].is_admin,
                pair[0].chat_type.value,
                pair[0].title.lower() if pair[0].title else "",
                pair[0].external_id or "",
                pair[0].chat_id.hex,
            ),
        )

        log.i(f"  Returning {len(results)} chats")
        return [
            chat_to_api(chat = chat_config, membership = membership, is_own = is_own_chat(chat_config, self.__di.invoker))
            for chat_config, membership in results
        ]

    def fetch_chat_settings(self, chat_id: str) -> ChatSettingsResponse:
        log.d(f"Fetching chat settings for chat '{chat_id}'")
        chat_config = self.__di.authorization_service.validate_chat(chat_id)

        membership = self.__di.authorization_service.update_chat_authorization(self.__di.invoker, chat_config)
        return chat_to_api(chat = chat_config, membership = membership, is_own = is_own_chat(chat_config, self.__di.invoker))

    def save_chat_settings(self, chat_id: str, payload: ChatSettingsPayload) -> None:
        log.d(f"Saving chat settings for chat '{chat_id}'")
        if payload.chat_config is None and payload.user_chat_config is None:
            raise ValidationError(
                "Payload must contain at least one of 'chat_config' or 'user_chat_config'",
                EMPTY_CHAT_SETTINGS_PAYLOAD,
            )
        chat_config = self.__di.authorization_service.validate_chat(chat_id)

        # chat_config write requires admin rights
        if payload.chat_config is not None:
            self.__di.authorization_service.validate_chat_admin(self.__di.invoker, chat_config)
            self.__apply_chat_config_changes(chat_config, payload.chat_config)

        # user_chat_config write is allowed for any member (membership is created on demand)
        if payload.user_chat_config is not None:
            self.__apply_user_chat_config_changes(self.__di.invoker, chat_config, payload.user_chat_config)

        log.i("Chat settings saved")

    def __apply_user_chat_config_changes(
        self, user: User, chat_config: ChatConfig, payload: UserChatConfigPayload,
    ) -> None:
        log.t(
            "  Updating user_chat_config: "
            f"use_about_me={payload.use_about_me}, "
            f"use_custom_prompt={payload.use_custom_prompt}, "
            f"max_output_tokens={payload.max_output_tokens}, "
            f"max_chat_history_depth={payload.max_chat_history_depth}, "
            f"max_iterations={payload.max_iterations}",
        )
        membership = self.__di.chat_membership_service.sync(user, chat_config)
        self.__di.chat_membership_service.save(
            ChatMembership(
                user_id = membership.user_id,
                chat_id = membership.chat_id,
                is_admin = membership.is_admin,
                use_about_me = payload.use_about_me,
                use_custom_prompt = payload.use_custom_prompt,
                max_output_tokens = payload.max_output_tokens,
                max_chat_history_depth = payload.max_chat_history_depth,
                max_iterations = payload.max_iterations,
            ),
        )

    def __apply_chat_config_changes(self, chat_config: ChatConfig, payload: ChatConfigPayload) -> None:
        # validate language changes
        if not payload.language_name or not payload.language_iso_code:
            raise ValidationError("Both language_name and language_iso_code must be non-empty", INVALID_LANGUAGE_SETTINGS)
        log.t(f"  Updating language to '{payload.language_name}' ({payload.language_iso_code})")

        # validate reply chance changes
        if chat_config.is_private and payload.reply_chance_percent != 100:
            raise ValidationError("Chat is private, reply chance cannot be changed", INVALID_REPLY_CHANCE)
        log.t(f"  Updating reply chance to {payload.reply_chance_percent}%")

        # validate release notifications changes
        release_notifications = ChatConfigDB.ReleaseNotifications.lookup(payload.release_notifications)
        if not release_notifications:
            raise ValidationError(f"Invalid release notifications setting value '{payload.release_notifications}'", INVALID_RELEASE_NOTIFICATIONS)  # noqa: E501
        log.t(f"  Updating release notifications to '{release_notifications.value}'")

        # validate media mode changes
        media_mode = ChatConfigDB.MediaMode.lookup(payload.media_mode)
        if not media_mode:
            raise ValidationError(f"Invalid media mode setting value '{payload.media_mode}'", INVALID_MEDIA_MODE)
        log.t(f"  Updating media mode to '{media_mode.value}'")

        updated_chat_config = replace(
            chat_config,
            language_name = payload.language_name,
            language_iso_code = payload.language_iso_code,
            reply_chance_percent = payload.reply_chance_percent,
            release_notifications = release_notifications,
            media_mode = media_mode,
        )

        self.__di.chat_config_repo.save(updated_chat_config)

    def save_user_settings(self, user_id_hex: str, payload: UserSettingsPayload):
        log.d(f"Saving user settings for user '{user_id_hex}'")
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)

        # validate tool choices
        all_tool_ids = {tool.id for tool in ALL_EXTERNAL_TOOLS}
        for key, value in payload.model_dump().items():
            if key.startswith("tool_choice_") and value and (value not in all_tool_ids):
                raise ValidationError(f"Invalid tool choice '{value}' for '{key}'. Tool is not recognized.", INVALID_TOOL_CHOICE)

        if payload.are_policies_accepted is False:
            raise ValidationError(
                "Policy acceptance cannot be revoked once accepted",
                POLICY_ACCEPTANCE_REVOCATION_FORBIDDEN,
            )
        should_activate_waitlisted_user = (
            payload.are_policies_accepted is True and
            user.is_on_waitlist
        )
        if should_activate_waitlisted_user:
            self.__di.authorization_service.require_waitlisted_user_can_activate(user)

        user_save = api_to_domain(payload, user)
        if should_activate_waitlisted_user:
            user_save.is_on_waitlist = False
            user_save.is_invited_to_start = False
        User.model_validate(self.__di.user_crud.save(user_save))
        log.i("User settings saved")

    def __is_sponsored(self, user_id: UUID) -> bool:
        return bool(self.__di.sponsorship_repo.get_all_by_receiver(user_id))

    def __create_jwt_token(self, chat_type: ChatConfigDB.ChatType) -> str:
        external_id = resolve_external_id(self.__di.invoker, chat_type)
        external_handle = resolve_external_handle(self.__di.invoker, chat_type)

        # Get platform-agnostic issuer name
        agent_user = resolve_agent_user(chat_type)
        issuer_name = agent_user.full_name or config.background_bot_name  # fallback for backward compatibility

        token_payload = {
            "iss": issuer_name,  # issuer, app name
            "sub": self.__di.invoker.id.hex,  # subject, user's unique identifier
            "platform": chat_type.value,  # origin of the token
            **({"platform_id": external_id} if external_id else {}),
            **({"platform_handle": external_handle} if external_handle else {}),
        }
        return auth.create_jwt_token(token_payload, config.jwt_expires_in_minutes)
