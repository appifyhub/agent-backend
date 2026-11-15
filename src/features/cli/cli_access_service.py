import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from dateutil.relativedelta import relativedelta

from api.auth import create_cli_jwt_token
from di.di import DI
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integrations import resolve_best_notification_chat
from features.users.user import User, generate_connect_key
from util import log
from util.error_codes import (
    ANNOUNCEMENT_NOT_RECEIVED,
    CLI_TTL_TOO_LONG,
    CONNECT_KEY_NOT_FOUND,
    INSUFFICIENT_CREDITS,
    INVALID_CLI_DEVICE,
    INVALID_CLI_TTL,
)
from util.errors import BadRequestError, ExternalServiceError, NotFoundError, ValidationError

DEFAULT_CLI_TOKEN_TTL = relativedelta(months = 6)
MAX_CLI_TOKEN_TTL = relativedelta(years = 2)
TTL_PATTERN = re.compile(r"([1-9][0-9]*)(s|min|m|h|d|mo|M|y)")
TTL_MAX_DIGITS = 9

HOSTNAME_PATTERN = re.compile(r"[A-Za-z0-9.-]{1,32}")
OS_PATTERN = re.compile(r"[A-Za-z0-9._/-]{1,32}")


class CliAccessService:

    @dataclass(frozen = True)
    class Connection:
        token: str
        expires_at: datetime
        user: User

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def connect(self, ttl_as_text: str | None, device_id: str, hostname: str, os: str) -> Connection:
        # resolve the basic connection parameters first
        now = datetime.now(timezone.utc).replace(microsecond = 0)
        expires_at = self.__resolve_expiry(ttl_as_text, now)
        canonical_device_id = self.__validate_device(device_id, hostname, os)

        def rotate_key(locked: User) -> User:
            if locked.connect_key != self.__di.invoker.connect_key:
                raise NotFoundError("Connect key not found", CONNECT_KEY_NOT_FOUND)
            return replace(locked, connect_key = generate_connect_key())

        # rotate the key and create the token (rolling back if either fails)
        try:
            owner = self.__di.user_repo.update_locked(self.__di.invoker.id, rotate_key, commit = False)
            token = create_cli_jwt_token(
                user_id = owner.id.hex,
                generation = owner.cli_token_generation,
                device_id = canonical_device_id,
                hostname = hostname,
                os = os,
                expires_at = expires_at,
            )
            self.__di.db.commit()
        except Exception:
            self.__di.db.rollback()
            raise

        # finally send the notification and exit
        log.i(f"CLI connected for user '{owner.id.hex}' from '{hostname}'")
        self.__send_new_device_alert(hostname, os, expires_at)
        user = cast(User, self.__di.user_repo.get(owner.id))  # needed as alert spends credits
        return CliAccessService.Connection(token = token, expires_at = expires_at, user = user)

    def revoke_all(self) -> None:
        self.__di.user_repo.update_locked(
            user_id = self.__di.invoker.id,
            update_fn = lambda locked: replace(locked, cli_token_generation = locked.cli_token_generation + 1),
        )
        log.i(f"Revoked all CLI access for user '{self.__di.invoker.id.hex}'")

    # noinspection PyMethodMayBeStatic
    def __resolve_expiry(self, ttl_as_text: str | None, now: datetime) -> datetime:
        # run the basic validations
        if ttl_as_text is None:
            return now + DEFAULT_CLI_TOKEN_TTL
        match = TTL_PATTERN.fullmatch(ttl_as_text)
        if match is None:
            raise BadRequestError(
                "Invalid token lifetime. Use a positive whole number followed by one unit: "
                "s, m (or min), h, d, mo (or M), or y, for example 12h, 30d, or 6mo.",
                INVALID_CLI_TTL,
            )
        amount_as_text, unit = match.groups()
        too_long = BadRequestError("Token lifetime is too long. The maximum is 2 years (2y, 24mo, or 730d).", CLI_TTL_TOO_LONG)
        if len(amount_as_text) > TTL_MAX_DIGITS:
            raise too_long

        # finally compute the delta and find the timestamp
        try:
            expires_at = now + self.__resolve_delta(int(amount_as_text), unit)
            latest_allowed = now + MAX_CLI_TOKEN_TTL
        except (OverflowError, ValueError) as e:
            raise too_long from e
        if expires_at > latest_allowed:
            raise too_long
        return expires_at

    # noinspection PyMethodMayBeStatic
    def __resolve_delta(self, amount: int, unit: str) -> timedelta | relativedelta:
        match unit:
            case "s":
                return timedelta(seconds = amount)
            case "m" | "min":
                return timedelta(minutes = amount)
            case "h":
                return timedelta(hours = amount)
            case "d":
                return timedelta(days = amount)
            case "mo" | "M":
                return relativedelta(months = amount)
            case _:
                return relativedelta(years = amount)

    # noinspection PyMethodMayBeStatic
    def __validate_device(self, device_id: str, hostname: str, os: str) -> str:
        try:
            canonical_device_id = str(UUID(device_id))
        except ValueError as e:
            raise ValidationError("Device ID must be a UUID", INVALID_CLI_DEVICE) from e
        if not HOSTNAME_PATTERN.fullmatch(hostname):
            raise ValidationError("Hostname must be 1 to 32 letters, digits, '.' or '-'", INVALID_CLI_DEVICE)
        if not OS_PATTERN.fullmatch(os):
            raise ValidationError("Operating system must be 1 to 32 letters, digits, '.', '_', '/' or '-'", INVALID_CLI_DEVICE)
        return canonical_device_id

    def __send_new_device_alert(self, hostname: str, os: str, expires_at: datetime) -> None:
        owner = self.__di.invoker
        try:
            # validate announcement destination
            chat = resolve_best_notification_chat(owner, self.__di)
            if chat is None:
                log.i(f"No chat can receive the new CLI alert for user '{owner.id.hex}'")
                return
            self.__di.spending_service.validate_message_delivery_pre_flight(chat, owner.id)
            self.__di.rollback_db_session()

            # prepare the announcement
            expiry = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
            raw_message = (
                f"A new command line client connected: {hostname} ({os}), valid until {expiry} UTC. "
                "If this was not you, open the agent's settings and revoke all CLI access!"
            )
            configured_tool = self.__di.tool_choice_resolver.require_tool(SysAnnouncementsService.TOOL_TYPE, default_tool_for(SysAnnouncementsService.TOOL_TYPE))  # ruff: ignore[line-too-long]
            chat, announcement = self.__di.sys_announcements_service(raw_message, chat, configured_tool).execute()
            if not announcement.content:
                raise ExternalServiceError("LLM announcement not received", ANNOUNCEMENT_NOT_RECEIVED)
            self.__di.rollback_db_session()

            # finally launch the message announcement
            chat_di = self.__di.clone(invoker_chat_id = chat.chat_id.hex)
            chat_di.platform_bot_sdk().send_text_message(str(chat.external_id), str(announcement.content))
            log.i(f"New CLI alert sent to user '{owner.id.hex}' on {chat.chat_type.value}")
        except Exception as e:
            if isinstance(e, ValidationError) and e.error_code == INSUFFICIENT_CREDITS:
                log.w(f"Skipping new CLI alert for user '{owner.id.hex}' due to insufficient delivery credits")
            else:
                log.e(f"Failed to send new CLI alert to user '{owner.id.hex}'", e)
