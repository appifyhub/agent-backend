from dataclasses import replace
from uuid import UUID

from di.di import DI
from features.accounting.usage.usage_record import UsageRecord
from features.chat.config.chat_config import ChatConfig
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations.integrations import delivery_tool_for, is_the_agent, resolve_private_chat_id
from features.users.user import User
from util import log
from util.config import config
from util.error_codes import INSUFFICIENT_CREDITS, USER_NOT_FOUND
from util.errors import NotFoundError, ValidationError


class SpendingService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_pre_flight(
        self,
        configured_tool: ConfiguredTool,
        max_output_tokens: int = config.default_max_output_tokens,
        input_text: str = "",
        search_tokens: int = 0,
        runtime_seconds: float = 0.0,
        input_image_sizes: list[str] | None = None,
        output_image_sizes: list[str] | None = None,
        output_video_size: str | None = None,
        output_video_duration_seconds: float | None = None,
    ) -> None:
        if not configured_tool.uses_credits:
            return
        estimated_cost = configured_tool.definition.cost_estimate.get_minimum_for(
            input_text = input_text,
            max_output_tokens = max_output_tokens,
            search_tokens = search_tokens,
            runtime_seconds = runtime_seconds,
            input_image_sizes = input_image_sizes,
            output_image_sizes = output_image_sizes,
            output_video_size = output_video_size,
            output_video_duration_seconds = output_video_duration_seconds,
        ) + config.usage_maintenance_fee_credits
        user = self.__di.user_repo.get(configured_tool.payer_id)
        if user is None:
            raise NotFoundError(f"Payer user not found for id {configured_tool.payer_id}", USER_NOT_FOUND)
        if user.credit_balance < estimated_cost:
            raise ValidationError(f"Insufficient credits: minimum required {estimated_cost}, available {user.credit_balance}", INSUFFICIENT_CREDITS)  # noqa: E501

    def validate_message_delivery_pre_flight(self, chat: ChatConfig, payer_id: UUID) -> None:
        payer = self.__di.user_repo.get(payer_id)
        if payer is None:
            raise NotFoundError(f"Payer user not found for id {payer_id}", USER_NOT_FOUND)

        charges = self.__resolve_message_delivery_charges(chat)
        minimum_required = sum(charges.values())
        if minimum_required > 0 and payer.credit_balance < minimum_required:
            message = f"Insufficient credits for message delivery: minimum required {minimum_required}, available {payer.credit_balance}"  # ruff: ignore[line-too-long]
            raise ValidationError(message, INSUFFICIENT_CREDITS)

    def deduct(self, configured_tool: ConfiguredTool, amount: float) -> None:
        if not configured_tool.uses_credits:
            return

        def apply(user):
            available = user.credit_balance or 0.0
            if amount > available:
                log.w(
                    f"Actual cost {amount} exceeds pre-flight estimate for user "
                    f"{configured_tool.payer_id}; balance will go negative",
                )
            return replace(user, credit_balance = available - amount)
        self.__di.user_repo.update_locked(configured_tool.payer_id, apply)

    def charge_for_message_delivery(self, chat: ChatConfig, payer_id: UUID):
        charges = self.__resolve_message_delivery_charges(chat)
        if not charges:
            return
        total = sum(charges.values())

        def charge(user: User) -> User:
            for recipient_id, amount in charges.items():
                # we flush all after the locked user update automatically
                self.__di.usage_record_repo.create(
                    UsageRecord(
                        user_id = user.id,
                        payer_id = user.id,
                        counterpart_id = recipient_id,
                        chat_id = chat.chat_id,
                        tool = delivery_tool_for(chat.chat_type),
                        tool_purpose = ToolType.message_delivery,
                        uses_credits = True,
                        runtime_seconds = 0,
                        model_cost_credits = 0,
                        remote_runtime_cost_credits = 0,
                        api_call_cost_credits = amount,
                        maintenance_fee_credits = 0,
                        total_cost_credits = amount,
                    ),
                    commit = False,
                )
            return replace(user, credit_balance = user.credit_balance - total)

        self.__di.user_repo.update_locked(payer_id, charge)

    def reconcile_message_delivery(self, chat: ChatConfig, recipient: User, is_delivery_free: bool) -> bool:
        delivery = self.__di.usage_record_repo.get_latest_unreconciled_delivery(chat.chat_id, recipient.id)
        if delivery is None:
            return False

        if not is_delivery_free:
            self.__di.usage_record_repo.mark_latest_delivery_reconciled(chat.chat_id, recipient.id)
            return True

        def correct(user: User) -> User:
            # we flush after the locked user update automatically
            delta = self.__di.usage_record_repo.reconcile_latest_delivery(chat.chat_id, 0.0, recipient.id, commit = False)
            if not delta:
                return user
            return replace(user, credit_balance = user.credit_balance - delta)

        self.__di.user_repo.update_locked(delivery.payer_id, correct)
        return True

    def __resolve_message_delivery_charges(self, chat: ChatConfig) -> dict[UUID, float]:
        charges: dict[UUID, float] = {}
        for membership in self.__di.chat_membership_repo.get_all_for_chat(chat.chat_id):
            recipient = self.__di.user_repo.get(membership.user_id)
            if recipient is None:
                raise NotFoundError(f"Delivery recipient not found for user {membership.user_id}", USER_NOT_FOUND)
            if is_the_agent(recipient, chat.chat_type):
                continue
            private_id = resolve_private_chat_id(recipient, chat.chat_type)
            amount = self.__di.messaging_price_service.get(chat.chat_type, private_id or "")
            if amount > 0:
                charges[recipient.id] = amount
        return charges
