from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.accounting.usage.participant_details import ParticipantDetails
from features.accounting.usage.usage_record import UsageRecord
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import TRANSFER_TOOL
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integration_config import THE_AGENT
from features.integrations.integrations import (
    format_handle,
    lookup_user_by_handle,
    resolve_best_notification_chat,
    resolve_external_handle,
    user_to_participant,
)
from features.users.user import User
from util import log
from util.error_codes import (
    ANNOUNCEMENT_NOT_RECEIVED,
    INSUFFICIENT_CREDITS,
    INVALID_TRANSFER_AMOUNT,
    SELF_TRANSFER_NOT_ALLOWED,
    SPONSORED_USER_TRANSFER_NOT_ALLOWED,
    TRANSFER_FAILED,
    TRANSFER_RECIPIENT_NOT_FOUND,
    USER_NOT_FOUND,
)
from util.errors import ExternalServiceError, InternalError, NotFoundError, ServiceError, ValidationError

MIN_TRANSFER_AMOUNT = 1.0


class CreditTransferService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def transfer_credits(
        self,
        sender_id: UUID,
        recipient_handle: str,
        chat_type: ChatConfigDB.ChatType,
        amount: float,
        note: str | None = None,
    ) -> None:
        log.d(f"Transfer request: {sender_id} -> {chat_type.value}/'@{recipient_handle}', amount = {amount}")
        started_at = datetime.now(timezone.utc)

        # run the basic validations, excluding credit balance (which requires a user lock)
        sender_user, receiver_user = self.__validate_transfer(sender_id, recipient_handle, chat_type, amount)

        # happens during the lock phase
        def apply_transfer(sender_user: User, receiver_user: User) -> tuple[User, User]:
            if sender_user.credit_balance < amount:
                raise ValidationError(
                    f"Not enough credits to transfer {amount} (balance: {sender_user.credit_balance})",
                    INSUFFICIENT_CREDITS,
                )
            return (
                replace(sender_user, credit_balance = sender_user.credit_balance - amount),
                replace(receiver_user, credit_balance = receiver_user.credit_balance + amount),
            )

        # acquire a lock and perform the credit transfer
        try:
            self.__di.user_repo.update_locked_pair(sender_user.id, receiver_user.id, apply_transfer)
        except ServiceError:
            raise
        except Exception as e:
            raise InternalError(f"Credit transfer failed: {e}", TRANSFER_FAILED) from e

        # update usage records to reflect this transfer
        self.__create_transfer_record(sender_user, receiver_user, amount, note, started_at)
        log.i(f"Transfer completed: {sender_user.id} -> {receiver_user.id}, amount = {amount}")

        # and finally notify the participants
        self.__try_to_notify_sender(sender_user, recipient_handle, chat_type, amount)
        self.__try_to_notify_receiver(receiver_user, sender_user, chat_type, amount, note)

    def grant_credits(
        self,
        recipient: User | UUID,
        amount: float,
        commit: bool,
        note: str | None = None,
    ) -> User:
        recipient_id = recipient if isinstance(recipient, UUID) else recipient.id
        if recipient_id is None:
            raise NotFoundError("Grant recipient has not been persisted", USER_NOT_FOUND)

        started_at = datetime.now(timezone.utc)
        log.d(f"Granting {amount} credits to {recipient_id}...")

        def mint_agent_credits(agent_user: User, recipient_user: User) -> tuple[User, User]:
            return replace(agent_user, credit_balance = agent_user.credit_balance + amount), recipient_user

        def apply_transfer(agent_user: User, recipient_user: User) -> tuple[User, User]:
            return (
                replace(agent_user, credit_balance = agent_user.credit_balance - amount),
                replace(recipient_user, credit_balance = recipient_user.credit_balance + amount),
            )

        try:
            # first we mint the credits for The Agent's account
            self.__di.user_repo.update_locked_pair(
                first_id = THE_AGENT.id,
                second_id = recipient_id,
                update_fn = mint_agent_credits,
                commit = False,
            )
            # then we transfer them to the granted user
            updated_agent, updated_recipient = self.__di.user_repo.update_locked_pair(
                first_id = THE_AGENT.id,
                second_id = recipient_id,
                update_fn = apply_transfer,
                commit = False,
            )
            # and finally, keep a record of the grant for bookkeeping purposes
            self.__create_transfer_record(
                sender_user = updated_agent,
                receiver_user = updated_recipient,
                amount = amount,
                note = note,
                started_at = started_at,
                commit = False,
            )
            if commit:
                self.__di.db.commit()
        except ServiceError:
            self.__di.db.rollback()
            raise
        except Exception as e:
            self.__di.db.rollback()
            raise InternalError(f"Credit grant failed for recipient {recipient_id}: {e}", TRANSFER_FAILED) from e

        if commit:
            self.notify_grant(updated_recipient, amount, note)
        return updated_recipient

    def notify_grant(self, recipient: User, amount: float, note: str | None = None):
        log.i(f"Granted {amount} credits to {recipient.id}")
        message = f"You have been granted {amount} credits"
        if note:
            message += f" for \"{note}\""
        message += ". Enjoy!"
        self.__try_to_send_notification(recipient, message)

    def __create_transfer_record(
        self,
        sender_user: User,
        receiver_user: User,
        amount: float,
        note: str | None,
        started_at: datetime,
        commit: bool = True,
    ):
        sender_info = user_to_participant(sender_user)
        receiver_info = user_to_participant(receiver_user)

        now = datetime.now(timezone.utc)
        runtime_seconds = (now - started_at).total_seconds()
        record = UsageRecord(
            user_id = sender_user.id,
            payer_id = sender_user.id,
            uses_credits = True,
            is_failed = False,
            chat_id = self.__di.invoker_chat.chat_id if self.__di.invoker_chat else None,
            tool = TRANSFER_TOOL,
            tool_purpose = ToolType.credit_transfer,
            timestamp = now,
            runtime_seconds = runtime_seconds,
            model_cost_credits = 0.0,
            remote_runtime_cost_credits = 0.0,
            api_call_cost_credits = 0.0,
            maintenance_fee_credits = 0.0,
            total_cost_credits = amount,
            counterpart_id = receiver_user.id,
            note = note,
            participant_details = ParticipantDetails(
                payer = sender_info,
                owner = sender_info,
                counterpart = receiver_info,
            ),
        )
        self.__di.usage_record_repo.create(record, commit = commit)

    def __validate_transfer(
        self,
        sender_id: UUID,
        recipient_handle: str,
        chat_type: ChatConfigDB.ChatType,
        amount: float,
    ) -> tuple[User, User]:
        if amount < MIN_TRANSFER_AMOUNT:
            raise ValidationError(
                f"Transfer amount must be at least {MIN_TRANSFER_AMOUNT} credits",
                INVALID_TRANSFER_AMOUNT,
            )

        sender_user = self.__di.user_repo.get(sender_id)
        if not sender_user:
            raise NotFoundError(f"Sender '{sender_id}' not found", USER_NOT_FOUND)

        receiver_user = lookup_user_by_handle(recipient_handle, chat_type, self.__di.user_repo)
        if not receiver_user:
            raise NotFoundError(
                f"Recipient '@{recipient_handle}' not found on {chat_type.value}",
                TRANSFER_RECIPIENT_NOT_FOUND,
            )

        if sender_user.id == receiver_user.id:
            raise ValidationError("Cannot transfer credits to yourself", SELF_TRANSFER_NOT_ALLOWED)

        if self.__di.sponsorship_repo.get_all_by_receiver(sender_user.id, limit = 1):
            raise ValidationError("Sponsored users cannot transfer credits", SPONSORED_USER_TRANSFER_NOT_ALLOWED)

        if self.__di.sponsorship_repo.get_all_by_receiver(receiver_user.id, limit = 1):
            raise ValidationError("Cannot transfer credits to a sponsored user", SPONSORED_USER_TRANSFER_NOT_ALLOWED)

        return sender_user, receiver_user

    def __try_to_notify_sender(
        self, sender: User, recipient_handle: str, chat_type: ChatConfigDB.ChatType, amount: float,
    ):
        formatted = format_handle(recipient_handle, chat_type)
        self.__try_to_send_notification(sender, f"You sent {amount} credits to {formatted}.")

    def __try_to_notify_receiver(
        self, receiver: User, sender: User, chat_type: ChatConfigDB.ChatType, amount: float, note: str | None,
    ):
        sender_handle = resolve_external_handle(sender, chat_type)
        sender_label = format_handle(sender_handle, chat_type) if sender_handle else sender.full_name or "an anonymous user"
        parts = [f"You received {amount} credits from {sender_label}."]
        if note:
            parts.append(f"Note from the sender: {note}")
        self.__try_to_send_notification(receiver, "\n".join(parts))

    def __try_to_send_notification(self, target: User, raw_message: str):
        log.d(f"Trying to send transfer notification to user {target.id.hex}...")
        try:
            target_chat = resolve_best_notification_chat(target, self.__di)
            if not target_chat:
                log.d(f"No eligible chat found for user {target.id.hex}, skipping notification")
                return

            configured_tool = self.__di.tool_choice_resolver.require_tool(
                SysAnnouncementsService.TOOL_TYPE,
                default_tool_for(SysAnnouncementsService.TOOL_TYPE),
            )

            target_chat, announcement = self.__di.sys_announcements_service(
                raw_message,
                target_chat = target_chat,
                configured_tool = configured_tool,
            ).execute()
            if not announcement.content:
                raise ExternalServiceError("LLM announcement not received", ANNOUNCEMENT_NOT_RECEIVED)

            chat_scoped_di = self.__di.clone(invoker_chat_id = target_chat.chat_id.hex)
            chat_scoped_di.platform_bot_sdk().send_text_message(str(target_chat.external_id), str(announcement.content))
            log.i(f"Transfer notification sent to user {target.id.hex} on {target_chat.chat_type.value}")
        except Exception as e:
            log.e(f"Failed to send transfer notification to user {target.id.hex}", e)
