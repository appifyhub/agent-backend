from dataclasses import replace
from enum import Enum
from uuid import UUID

from db.model.chat_message import ChatMessageDB
from db.model.price_alert import PriceAlertDB
from db.model.sponsorship import SponsorshipDB
from db.model.user import UserDB
from di.di import DI
from features.users.user import User, generate_connect_key
from util import log
from util.error_codes import CONNECT_KEY_UPDATE_FAILED, USER_DELETE_FAILED
from util.errors import InternalError


class ProfileConnectService:

    class Result(Enum):
        success = "success"
        failure = "failure"

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def connect_profiles(self, requester_user: User, target_connect_key: str) -> tuple[Result, str]:
        log.d(f"User '{requester_user.id}' requesting to connect with another profile")
        log.t(f"  Using connect-key: '{target_connect_key}'")

        # Find target user by connect key
        target_user = self.__di.user_repo.get_by_connect_key(target_connect_key)
        if not target_user:
            return (
                ProfileConnectService.Result.failure,
                "Invalid connect key. Please check the key and try again.",
            )

        # Validate merge
        validation_error = self.__validate_connection(requester_user, target_user)
        if validation_error:
            return ProfileConnectService.Result.failure, validation_error

        # Perform merge in transaction
        survivor_user, casualty_user = self.__classify_profiles(requester_user, target_user)
        log.d(f"Survivor: '{survivor_user.id}' (created {survivor_user.created_at})")
        log.d(f"Casualty: '{casualty_user.id}' (created {casualty_user.created_at})")

        try:
            # Check if a transaction is already running; if not, start one
            if not self.__di.db.in_transaction():
                self.__di.db.begin()

            # Migrate related records BEFORE merging user data
            self.__migrate_dependent_entities(survivor_user.id, casualty_user.id)

            # Merge user data first (reads from casualty_user before deletion)
            merged_user = self.__merge_user_data(survivor_user, casualty_user)

            # Delete the casualty profile (frees up unique constraints for the survivor's update)
            deleted_user = self.__di.user_repo.delete(casualty_user.id, commit = False)
            if not deleted_user:
                raise InternalError(f"Failed to find user to delete '{casualty_user.id}'", USER_DELETE_FAILED)
            merged_user = self.__di.user_repo.save(merged_user, commit = False)

            # Regenerate connect key for survivor
            log.d("Generating new connect key for the survivor user")
            self.regenerate_connect_key(merged_user, commit = False)

            # Commit all changes atomically
            self.__di.db.commit()

            log.i("Successfully connected profiles!")
            log.d(f"  Survivor: '{survivor_user.id}'")
            log.d(f"  Casualty: '{casualty_user.id}'")

            return (
                ProfileConnectService.Result.success,
                "Profiles connected successfully! Data was merged and you have a new connect key on the new joint profile.",
            )
        except Exception as e:
            self.__di.db.rollback()
            log.e("Failed to connect profiles", e)
            return ProfileConnectService.Result.failure, f"Failed to connect profiles: {e}"

    def regenerate_connect_key(self, user: User, commit: bool = True) -> str:
        log.d(f"Regenerating connect key for user '{user.id}'")
        updated_user = self.__di.user_repo.save(replace(user, connect_key = generate_connect_key()), commit = commit)
        if not updated_user:
            raise InternalError(f"Failed to update connect key for user '{user.id}'", CONNECT_KEY_UPDATE_FAILED)
        log.i(f"Generated new connect key for user '{user.id}'")
        return updated_user.connect_key

    def __validate_connection(self, requester: User, target: User) -> str | None:
        # Cannot connect to self
        if requester.id == target.id:
            return "Cannot connect a profile to itself."

        # Check platform compatibility - must have different platforms
        requester_has_telegram = requester.telegram_user_id is not None
        requester_has_whatsapp = requester.whatsapp_user_id is not None
        target_has_telegram = target.telegram_user_id is not None
        target_has_whatsapp = target.whatsapp_user_id is not None

        # Both must have at least one platform
        if not requester_has_telegram and not requester_has_whatsapp:
            return "Requester profile must have at least one platform (Telegram or WhatsApp)."
        if not target_has_telegram and not target_has_whatsapp:
            return "Target profile must have at least one platform (Telegram or WhatsApp)."

        # Must have different platforms (no TG+TG or WA+WA)
        if requester_has_telegram and target_has_telegram and not requester_has_whatsapp and not target_has_whatsapp:
            return "Both profiles have Telegram only. Profiles must have different platforms."
        if requester_has_whatsapp and target_has_whatsapp and not requester_has_telegram and not target_has_telegram:
            return "Both profiles have WhatsApp only. Profiles must have different platforms."

        return None

    def __classify_profiles(self, user1: User, user2: User) -> tuple[User, User]:
        # Survivor is the older user (earlier created_at)
        if user1.created_at <= user2.created_at:
            return user1, user2
        else:
            return user2, user1

    def __merge_user_data(self, survivor: User, casualty: User) -> User:
        log.d(f"Merging data from '{casualty.id}' into '{survivor.id}'")
        merged = replace(survivor)

        # Merge fields: prefer non-null from either, otherwise use survivor's value
        # For fields where both have values, prefer survivor (older account)
        if not merged.full_name and casualty.full_name:
            merged.full_name = casualty.full_name

        # Merge Telegram fields if survivor doesn't have them
        if not merged.telegram_user_id and casualty.telegram_user_id:
            merged.telegram_user_id = casualty.telegram_user_id
            merged.telegram_username = casualty.telegram_username
            merged.telegram_chat_id = casualty.telegram_chat_id

        # Merge WhatsApp fields if survivor doesn't have them
        if not merged.whatsapp_user_id and casualty.whatsapp_user_id:
            merged.whatsapp_user_id = casualty.whatsapp_user_id
            merged.whatsapp_phone_number = casualty.whatsapp_phone_number

        # Merge API keys: prefer non-null from either, survivor takes precedence if both set
        if not merged.open_ai_key and casualty.open_ai_key:
            merged.open_ai_key = casualty.open_ai_key
        if not merged.anthropic_key and casualty.anthropic_key:
            merged.anthropic_key = casualty.anthropic_key
        if not merged.google_ai_key and casualty.google_ai_key:
            merged.google_ai_key = casualty.google_ai_key
        if not merged.perplexity_key and casualty.perplexity_key:
            merged.perplexity_key = casualty.perplexity_key
        if not merged.replicate_key and casualty.replicate_key:
            merged.replicate_key = casualty.replicate_key
        if not merged.rapid_api_key and casualty.rapid_api_key:
            merged.rapid_api_key = casualty.rapid_api_key
        if not merged.coinmarketcap_key and casualty.coinmarketcap_key:
            merged.coinmarketcap_key = casualty.coinmarketcap_key
        if not merged.twelve_data_api_key and casualty.twelve_data_api_key:
            merged.twelve_data_api_key = casualty.twelve_data_api_key
        if not merged.x_key and casualty.x_key:
            merged.x_key = casualty.x_key
        if not merged.x_ai_key and casualty.x_ai_key:
            merged.x_ai_key = casualty.x_ai_key

        # Merge tool choices: prefer casualty's value when survivor lacks it
        if not merged.tool_choice_chat and casualty.tool_choice_chat:
            merged.tool_choice_chat = casualty.tool_choice_chat
        if not merged.tool_choice_reasoning and casualty.tool_choice_reasoning:
            merged.tool_choice_reasoning = casualty.tool_choice_reasoning
        if not merged.tool_choice_copywriting and casualty.tool_choice_copywriting:
            merged.tool_choice_copywriting = casualty.tool_choice_copywriting
        if not merged.tool_choice_vision and casualty.tool_choice_vision:
            merged.tool_choice_vision = casualty.tool_choice_vision
        if not merged.tool_choice_hearing and casualty.tool_choice_hearing:
            merged.tool_choice_hearing = casualty.tool_choice_hearing
        if not merged.tool_choice_images_gen and casualty.tool_choice_images_gen:
            merged.tool_choice_images_gen = casualty.tool_choice_images_gen
        if not merged.tool_choice_videos_gen and casualty.tool_choice_videos_gen:
            merged.tool_choice_videos_gen = casualty.tool_choice_videos_gen
        if not merged.tool_choice_images_edit and casualty.tool_choice_images_edit:
            merged.tool_choice_images_edit = casualty.tool_choice_images_edit
        if not merged.tool_choice_search and casualty.tool_choice_search:
            merged.tool_choice_search = casualty.tool_choice_search
        if not merged.tool_choice_embedding and casualty.tool_choice_embedding:
            merged.tool_choice_embedding = casualty.tool_choice_embedding
        if not merged.tool_choice_api_fiat_exchange and casualty.tool_choice_api_fiat_exchange:
            merged.tool_choice_api_fiat_exchange = casualty.tool_choice_api_fiat_exchange
        if not merged.tool_choice_api_crypto_exchange and casualty.tool_choice_api_crypto_exchange:
            merged.tool_choice_api_crypto_exchange = casualty.tool_choice_api_crypto_exchange
        if not merged.tool_choice_api_stock_quote and casualty.tool_choice_api_stock_quote:
            merged.tool_choice_api_stock_quote = casualty.tool_choice_api_stock_quote
        if not merged.tool_choice_api_twitter and casualty.tool_choice_api_twitter:
            merged.tool_choice_api_twitter = casualty.tool_choice_api_twitter
        merged.credit_balance = survivor.credit_balance + casualty.credit_balance

        # optimize for keeping the account active
        merged.are_policies_accepted = survivor.are_policies_accepted or casualty.are_policies_accepted
        merged.is_on_waitlist = survivor.is_on_waitlist and casualty.is_on_waitlist
        if merged.is_on_waitlist:
            # will remain on the waitlist – preserve the invite
            merged.is_invited_to_start = survivor.is_invited_to_start or casualty.is_invited_to_start
        else:
            merged.is_invited_to_start = False  # no waiting, reset the invite flag

        # Keep survivor's group (developer group takes precedence to not lose admin rights)
        if casualty.group == UserDB.Group.developer or survivor.group == UserDB.Group.developer:
            merged.group = UserDB.Group.developer

        return merged

    def __migrate_dependent_entities(self, survivor_user_id: UUID, casualty_user_id: UUID):
        log.d(f"Migrating related records from '{casualty_user_id}' to '{survivor_user_id}'")

        # Update chat messages
        self.__di.db.query(ChatMessageDB).filter(
            ChatMessageDB.author_id == casualty_user_id,
        ).update({ChatMessageDB.author_id: survivor_user_id}, synchronize_session = False)

        # Update price alerts
        self.__di.db.query(PriceAlertDB).filter(
            PriceAlertDB.owner_id == casualty_user_id,
        ).update({PriceAlertDB.owner_id: survivor_user_id}, synchronize_session = False)

        # Handle sponsorships where casualty user is the sponsor
        self.__di.db.query(SponsorshipDB).filter(
            SponsorshipDB.sponsor_id == casualty_user_id,
            SponsorshipDB.receiver_id == survivor_user_id,
        ).delete(synchronize_session = False)
        self.__di.db.query(SponsorshipDB).filter(
            SponsorshipDB.sponsor_id == casualty_user_id,
        ).update({SponsorshipDB.sponsor_id: survivor_user_id}, synchronize_session = False)

        # Handle sponsorships where casualty user is the receiver
        self.__di.db.query(SponsorshipDB).filter(
            SponsorshipDB.sponsor_id == survivor_user_id,
            SponsorshipDB.receiver_id == casualty_user_id,
        ).delete(synchronize_session = False)
        self.__di.db.query(SponsorshipDB).filter(
            SponsorshipDB.receiver_id == casualty_user_id,
        ).update({SponsorshipDB.receiver_id: survivor_user_id}, synchronize_session = False)
