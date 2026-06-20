from typing import Any

from api.model.sponsorship_payload import SponsorshipPayload
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.integrations.integrations import lookup_user_by_handle, resolve_any_external_handle
from features.sponsorships.sponsorship_service import SponsorshipService
from util import log
from util.config import config
from util.error_codes import INVALID_PLATFORM, SPONSORSHIP_OPERATION_FAILED, UNSPONSOR_SELF_FAILED
from util.errors import InternalError, ValidationError


class SponsorshipsController:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def fetch_sponsorships(self, user_id_hex: str) -> dict[str, Any]:
        log.d(f"Fetching sponsorships for user '{user_id_hex}'")
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        sponsorships = self.__di.sponsorship_repo.get_all_by_sponsor(user.id)
        max_sponsorships = (
            config.max_sponsorships_per_user
            if self.__di.invoker.group != UserDB.Group.developer
            else config.max_users
        )
        if not sponsorships:
            log.d("  No sponsorships found")
            return {
                "sponsorships": [],
                "max_sponsorships": max_sponsorships,
            }

        output_sponsorships: list[dict[str, Any]] = []
        for sponsorship in sponsorships:
            receiver_user_db = self.__di.user_crud.get(sponsorship.receiver_id)
            if not receiver_user_db:
                log.t(f"  Receiver user with id {sponsorship.receiver_id} not found, skipping.")
                continue
            receiver_user = User.model_validate(receiver_user_db)
            platform_handle, platform_type = resolve_any_external_handle(receiver_user)
            output_sponsorships.append(
                {
                    "user_id_hex": receiver_user.id.hex,
                    "full_name": receiver_user.full_name,
                    "platform_handle": platform_handle,
                    "platform": platform_type.value if platform_type else None,
                    "sponsored_at": sponsorship.sponsored_at.isoformat(),
                    "accepted_at": sponsorship.accepted_at.isoformat() if sponsorship.accepted_at else None,
                    "is_on_waitlist": receiver_user.is_on_waitlist,
                    "is_invited_to_start": receiver_user.is_invited_to_start,
                    "are_policies_accepted": receiver_user.are_policies_accepted,
                },
            )
        return {
            "sponsorships": output_sponsorships,
            "max_sponsorships": max_sponsorships,
        }

    def sponsor_user(self, sponsor_user_id_hex: str, payload: SponsorshipPayload) -> dict[str, Any]:
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, sponsor_user_id_hex)
        log.d(f"Sponsoring user {payload.platform}/'@{payload.platform_handle}' by '{self.__di.invoker.id.hex}'")
        chat_type = ChatConfigDB.ChatType.lookup(payload.platform)
        if not chat_type:
            raise ValidationError(f"Unsupported platform: {payload.platform}", INVALID_PLATFORM)
        result, message = self.__di.sponsorship_service.sponsor_user(
            sponsor_user_id_hex = user.id.hex,
            receiver_handle = payload.platform_handle,
            chat_type = chat_type,
        )
        if result == SponsorshipService.Result.failure:
            raise InternalError(message, SPONSORSHIP_OPERATION_FAILED)

        # user status changed possibly with regards to waitlist or start invitation – let's fetch
        receiver_user_db = lookup_user_by_handle(payload.platform_handle, chat_type, self.__di.user_crud)
        if not receiver_user_db:
            raise InternalError("Sponsored receiver user not found after sponsorship creation", SPONSORSHIP_OPERATION_FAILED)
        receiver_user = User.model_validate(receiver_user_db)
        sponsorship = self.__di.sponsorship_repo.get(user.id, receiver_user.id)
        if not sponsorship:
            raise InternalError("Sponsorship row not found after sponsorship creation", SPONSORSHIP_OPERATION_FAILED)
        platform_handle, platform_type = resolve_any_external_handle(receiver_user)
        log.i(f"  Successfully sponsored '@{payload.platform_handle}'")
        return {
            "status": "OK",
            "message": message,
            "sponsorship": {
                "user_id_hex": receiver_user.id.hex,
                "full_name": receiver_user.full_name,
                "platform_handle": platform_handle,
                "platform": platform_type.value if platform_type else None,
                "sponsored_at": sponsorship.sponsored_at.isoformat(),
                "accepted_at": sponsorship.accepted_at.isoformat() if sponsorship.accepted_at else None,
                "is_on_waitlist": receiver_user.is_on_waitlist,
                "is_invited_to_start": receiver_user.is_invited_to_start,
                "are_policies_accepted": receiver_user.are_policies_accepted,
            },
        }

    def unsponsor_user(self, sponsor_user_id_hex: str, platform: str, platform_handle: str):
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, sponsor_user_id_hex)
        log.d(f"Unsponsoring user {platform}/'@{platform_handle}' by '{self.__di.invoker.id.hex}'")
        chat_type = ChatConfigDB.ChatType.lookup(platform)
        if not chat_type:
            raise ValidationError(f"Unsupported platform: {platform}", INVALID_PLATFORM)
        result, message = self.__di.sponsorship_service.unsponsor_user(
            sponsor_user_id_hex = user.id.hex,
            receiver_handle = platform_handle,
            chat_type = chat_type,
        )
        if result == SponsorshipService.Result.failure:
            raise InternalError(message, SPONSORSHIP_OPERATION_FAILED)
        log.i(f"  Successfully unsponsored '@{platform_handle}'")

    def unsponsor_self(self, user_id_hex: str):
        user = self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        log.d(f"User '{user.id.hex}' is unsponsoring themselves")
        result, message = self.__di.sponsorship_service.unsponsor_self(user.id.hex)
        if result == SponsorshipService.Result.failure:
            raise InternalError(message, UNSPONSOR_SELF_FAILED)
        log.i("  Successfully unsponsored self")
