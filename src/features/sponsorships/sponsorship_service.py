from dataclasses import replace
from datetime import datetime
from enum import Enum
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.integrations.integrations import (
    lookup_user_by_handle,
    resolve_external_handle,
    resolve_external_id,
    resolve_user_to_save,
)
from features.sponsorships.sponsorship import Sponsorship
from util import log
from util.config import config


class SponsorshipService:

    class Result(Enum):
        success = "success"
        failure = "failure"

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def sponsor_user(
        self, sponsor_user_id_hex: str, receiver_handle: str, chat_type: ChatConfigDB.ChatType,
    ) -> tuple[Result, str]:
        log.d(f"Sponsor '{sponsor_user_id_hex}' is sponsoring {chat_type.value}/'@{receiver_handle}'")

        # check if sponsor exists
        sponsor_user_db = self.__di.user_crud.get(UUID(hex = sponsor_user_id_hex))
        if not sponsor_user_db:
            message = f"Sponsor '{sponsor_user_id_hex}' not found"
            log.d(message)
            return (SponsorshipService.Result.failure, message)
        sponsor_user = User.model_validate(sponsor_user_db)

        # check if sponsor is sponsoring themselves
        sponsor_handle = resolve_external_handle(sponsor_user, chat_type)
        if sponsor_handle == receiver_handle:
            message = f"Sponsor {chat_type.value}/'@{receiver_handle}' cannot sponsor themselves"
            log.d(message)
            return (SponsorshipService.Result.failure, message)

        # check if sponsor has exceeded the maximum number of sponsorships
        all_sponsor_sponsorships = self.__di.sponsorship_repo.get_all_by_sponsor(sponsor_user.id)
        is_sponsor_developer = sponsor_user.group == UserDB.Group.developer
        if len(all_sponsor_sponsorships) >= config.max_sponsorships_per_user and not is_sponsor_developer:
            message = f"Sponsor '{sponsor_user.id}' has exceeded the maximum number of sponsorships"
            log.d(message)
            return (SponsorshipService.Result.failure, message)

        # check if sponsor has any API key or credits
        if not sponsor_user.has_any_api_key() and sponsor_user.credit_balance <= 0:
            message = f"Sponsor '{sponsor_user.id}' has no API keys or credits configured"
            log.d(message)
            return (SponsorshipService.Result.failure, message)

        # check if sponsor is transitively sponsoring (sponsoring after being sponsored by someone else)
        all_sponsorships_received_by_sponsor = self.__di.sponsorship_repo.get_all_by_receiver(sponsor_user.id)
        if all_sponsorships_received_by_sponsor:
            message = f"Sponsor '{sponsor_user.id}' can't sponsor others while being sponsored themselves"
            log.d(message)
            return (SponsorshipService.Result.failure, message)

        # check if receiver already has a sponsorship
        receiver_user_db = lookup_user_by_handle(receiver_handle, chat_type, self.__di.user_crud)
        receiver_user: User
        if receiver_user_db:
            receiver_user = User.model_validate(receiver_user_db)
            # check if receiver already has a sponsorship
            all_receiver_sponsorships = self.__di.sponsorship_repo.get_all_by_receiver(receiver_user.id)
            if all_receiver_sponsorships:
                message = f"Receiver '@{receiver_handle}' already has a sponsorship"
                log.d(message)
                return (SponsorshipService.Result.failure, message)
            # check if receiver already has API keys - we don't want to override them
            if receiver_user.has_any_api_key():
                message = f"Receiver '@{receiver_handle}' already has API keys configured"
                log.d(message)
                return (SponsorshipService.Result.failure, message)
            # receiver is eligible to be sponsored
            external_id = resolve_external_id(receiver_user, chat_type)
            if external_id:
                log.t(f"Receiver '@{receiver_handle}' already has already messaged the bot")
                accepted_at = datetime.now()
            else:
                log.t(f"Receiver '@{receiver_handle}' has yet to message the bot")
                accepted_at = None
            receiver_handle_display = resolve_external_handle(receiver_user, chat_type) or receiver_handle
            message = f"Activated! Send a welcome message to user '@{receiver_handle_display}'"
        else:
            # create a new user for the receiver
            log.t(f"Creating new user for receiver {chat_type.value}/'@{receiver_handle}'")
            receiver_user_to_save = resolve_user_to_save(receiver_handle, chat_type)
            if not receiver_user_to_save:
                message = f"User creation not supported for platform {chat_type.value}"
                log.d(message)
                return (SponsorshipService.Result.failure, message)
            user_count = self.__di.user_crud.count()
            at_capacity = user_count >= config.max_users
            receiver_user_to_save.is_on_waitlist = at_capacity
            receiver_user_to_save.is_invited_to_start = False
            receiver_user_to_save.are_policies_accepted = False
            receiver_user_db = self.__di.user_crud.save(receiver_user_to_save)
            receiver_user = User.model_validate(receiver_user_db)
            accepted_at = None
            message = f"Sponsorship sent! Waiting for '{receiver_handle}' to send the first message"

        # finally, create a sponsorship to track the relationship
        sponsorship = self.__di.sponsorship_repo.save(
            Sponsorship(
                sponsor_id = sponsor_user.id,
                receiver_id = receiver_user.id,
                accepted_at = accepted_at,
            ),
        )
        log.i(f"Sponsorship created from '{sponsorship.sponsor_id}' to '{sponsorship.receiver_id}'")
        return SponsorshipService.Result.success, message

    def unsponsor_by_user_id(self, sponsor_id_hex: str, receiver_id_hex: str) -> tuple[Result, str]:
        log.d(f"Unsponsoring receiver '{receiver_id_hex}' by sponsor '{sponsor_id_hex}'")
        sponsor_id = UUID(hex = sponsor_id_hex)
        receiver_id = UUID(hex = receiver_id_hex)
        sponsorship = self.__di.sponsorship_repo.get(sponsor_id, receiver_id)
        if not sponsorship:
            message = f"No sponsorship from '{sponsor_id_hex}' to '{receiver_id_hex}'"
            log.d(message)
            return (SponsorshipService.Result.failure, message)
        self.__di.sponsorship_repo.delete(sponsor_id, receiver_id)
        log.d(f"Sponsorship from '{sponsor_id_hex}' to '{receiver_id_hex}' deleted")
        return (SponsorshipService.Result.success, "Sponsorship revoked!")

    def unsponsor_user(
        self, sponsor_user_id_hex: str, receiver_handle: str, chat_type: ChatConfigDB.ChatType,
    ) -> tuple[Result, str]:
        log.d(f"Sponsor '{sponsor_user_id_hex}' is unsponsoring receiver {chat_type.value}/'@{receiver_handle}'")

        # check if sponsor exists
        sponsor_user_db = self.__di.user_crud.get(UUID(hex = sponsor_user_id_hex))
        if not sponsor_user_db:
            message = f"Sponsor '{sponsor_user_id_hex}' not found"
            log.d(message)
            return (SponsorshipService.Result.failure, message)

        # check if receiver exists
        receiver_user_db = lookup_user_by_handle(receiver_handle, chat_type, self.__di.user_crud)
        if not receiver_user_db:
            message = f"Receiver '@{receiver_handle}' not found"
            log.d(message)
            return (SponsorshipService.Result.failure, message)
        receiver_user = User.model_validate(receiver_user_db)

        result, message = self.unsponsor_by_user_id(sponsor_user_id_hex, receiver_user.id.hex)
        if result == SponsorshipService.Result.success:
            handle_display = receiver_handle or resolve_external_handle(receiver_user, chat_type)
            return (result, f"Sponsorship revoked! Send a thanks/goodbye message to user '@{handle_display}'")
        return result, message

    def unsponsor_self(self, user_id_hex: str) -> tuple[Result, str]:
        log.d(f"User '{user_id_hex}' is unsponsoring themselves")
        user_db = self.__di.user_crud.get(UUID(hex = user_id_hex))
        if not user_db:
            message = f"User '{user_id_hex}' not found"
            log.d(message)
            return (SponsorshipService.Result.failure, message)
        user = User.model_validate(user_db)
        sponsorships = self.__di.sponsorship_repo.get_all_by_receiver(user.id)
        if not sponsorships:
            message = f"User '{user.id}' has no sponsorships to remove"
            log.d(message)
            return (SponsorshipService.Result.failure, message)
        sponsorship = sponsorships[0]
        return self.unsponsor_by_user_id(sponsorship.sponsor_id.hex, user_id_hex)

    def accept_sponsorship(self, receiver: User) -> bool:
        log.d(f"User '{receiver.id}' is trying to accept a sponsorship")

        # check if receiver already has API keys - don't accept sponsorship if they do
        if receiver.has_any_api_key():
            log.t(f"User '{receiver.id}' already has API keys configured, cannot accept sponsorship")
            return False

        # check if user has a sponsorship
        all_sponsorships = self.__di.sponsorship_repo.get_all_by_receiver(receiver.id)
        pending_sponsorships = [sponsorship for sponsorship in all_sponsorships if sponsorship.accepted_at is None]
        if not pending_sponsorships:
            log.t(f"User '{receiver.id}' has no pending sponsorships")
            return False

        # accept the sponsorship by updating its sponsorship_at timestamp
        sponsorship = self.__di.sponsorship_repo.save(replace(pending_sponsorships[0], accepted_at = datetime.now()))
        log.d(f"Sponsorship from '{sponsorship.sponsor_id}' to '{sponsorship.receiver_id}' accepted")
        return True
