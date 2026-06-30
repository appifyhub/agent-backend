from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from api.model.gumroad_ping_payload import GumroadPingPayload
from di.di import DI
from features.accounting.purchases.purchase_aggregates import PurchaseAggregates
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integration_config import THE_AGENT
from util import log
from util.config import config
from util.error_codes import ANNOUNCEMENT_NOT_RECEIVED
from util.errors import ExternalServiceError


class PurchaseService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def get_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        product_id: str | None = None,
    ) -> list[PurchaseRecord]:
        return self.__di.purchase_record_repo.get_by_user(
            user_id,
            skip = skip,
            limit = limit,
            start_date = start_date,
            end_date = end_date,
            product_id = product_id,
        )

    def get_aggregates_by_user(
        self,
        user_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        product_id: str | None = None,
    ) -> PurchaseAggregates:
        return self.__di.purchase_record_repo.get_aggregates_by_user(
            user_id,
            start_date = start_date,
            end_date = end_date,
            product_id = product_id,
        )

    def record_purchase(self, payload: GumroadPingPayload) -> PurchaseRecord | None:
        if payload.product_id not in config.products:
            log.w(f"Ignoring unknown product: {payload.product_id}")
            return None

        user_id: UUID | None = None
        if payload.url_params and "user_id" in payload.url_params:
            try:
                user_id_str = payload.url_params["user_id"]
                user_id = UUID(user_id_str)
                user = self.__di.user_repo.get(user_id)
                if user is None:
                    log.w(f"User {user_id_str} from url_params not found, storing without user_id")
                    user_id = None
            except (ValueError, KeyError) as e:
                log.w(f"Failed to parse user_id from url_params: {e}")
                user_id = None

        sale_timestamp = datetime.fromisoformat(payload.sale_timestamp.replace("Z", "+00:00"))

        record = PurchaseRecord(
            id = uuid4(),
            user_id = user_id,
            seller_id = payload.seller_id,
            sale_id = payload.sale_id,
            sale_timestamp = sale_timestamp,
            price = payload.price,
            product_id = payload.product_id,
            product_name = payload.product_name,
            product_permalink = payload.product_permalink,
            short_product_id = payload.short_product_id,
            license_key = payload.license_key,
            quantity = payload.quantity,
            gumroad_fee = payload.gumroad_fee,
            affiliate_credit_amount_cents = payload.affiliate_credit_amount_cents,
            discover_fee_charge = payload.discover_fee_charge,
            url_params = payload.url_params,
            custom_fields = payload.custom_fields,
            test = payload.test,
            is_preorder_authorization = payload.is_preorder_authorization,
            refunded = payload.refunded,
        )

        saved = self.__di.purchase_record_repo.save(record)
        self.__try_to_allocate_credits(saved)
        self.__try_to_deallocate_credits(saved)
        self.__try_to_notify_user(saved, is_license_bind = False)
        return saved

    def __get_credits_for_product(self, product_id: str) -> int:
        product = config.products.get(product_id)
        return product.credits if product is not None else 0

    def __try_to_allocate_credits(self, record: PurchaseRecord):
        if record.refunded or record.test or record.is_preorder_authorization:
            return
        if record.user_id is None:
            return
        credits = self.__get_credits_for_product(record.product_id)
        if credits <= 0:
            return
        total = float(credits * record.quantity)
        self.__di.user_repo.update_locked(
            user_id = record.user_id,
            update_fn = lambda user: replace(user, credit_balance = (user.credit_balance or 0.0) + total),
        )
        log.i(f"Allocated {total} credits to user {record.user_id} for purchase {record.id}")

    def __try_to_deallocate_credits(self, record: PurchaseRecord):
        if not record.refunded:
            return
        if record.user_id is None:
            return
        credits = self.__get_credits_for_product(record.product_id)
        if credits <= 0:
            return
        total = float(credits * record.quantity)
        self.__di.user_repo.update_locked(
            user_id = record.user_id,
            update_fn = lambda user: replace(user, credit_balance = (user.credit_balance or 0.0) - total),
        )
        log.i(f"Deallocated {total} credits from user {record.user_id} for purchase {record.id}")

    def bind_license_key(self, user_id: UUID, license_key: str) -> PurchaseRecord:
        saved = self.__di.purchase_record_repo.bind_license_key_to_user(license_key, user_id)
        self.__try_to_allocate_credits(saved)
        self.__try_to_notify_user(saved, is_license_bind = True)
        return saved

    def __try_to_notify_user(self, record: PurchaseRecord, is_license_bind: bool):
        log.d("Trying to notify user of a purchase...")

        if record.user_id is None:
            log.d("  Not notifying - user ID is missing")
            return
        if record.refunded or record.test or record.is_preorder_authorization:
            log.d(
                "  Not notifying - does not meet conditions!"
                "Refund = {record.refunded}, test = {record.test}, preorder = {record.is_preorder_authorization}",
            )
            return

        credits = self.__get_credits_for_product(record.product_id)
        total_credits = credits * record.quantity
        if total_credits <= 0:
            log.d("  Not notifying - product does not carry credits")
            return

        try:
            raw_message = " ".join([
                "Thank you for your purchase!",
                "Your license has been successfully bound." if is_license_bind else "Your purchase has been automatically bound.",
                f"You can now use your {total_credits} credits.",
            ])

            # take the token from the agent's user, as the current user's balance might not be enough
            agent_scoped_di = self.__di.clone(invoker_id = str(THE_AGENT.id))
            configured_tool = agent_scoped_di.tool_choice_resolver.require_tool(
                SysAnnouncementsService.TOOL_TYPE,
                default_tool_for(SysAnnouncementsService.TOOL_TYPE),
            )

            # initialize the announcements engine with the purchaser-user and no chat selection, ensuring the best delivery method
            user_scoped_di = self.__di.clone(invoker_id = str(record.user_id))
            target_chat, announcement = user_scoped_di.sys_announcements_service(
                raw_message,
                target_chat = None,
                configured_tool = configured_tool,
            ).execute()
            if not announcement.content:
                raise ExternalServiceError("LLM announcement not received", ANNOUNCEMENT_NOT_RECEIVED)

            # send the message to the user, into the target chat
            messaging_di = user_scoped_di.clone(invoker_chat_id = target_chat.chat_id.hex)
            messaging_di.platform_bot_sdk().send_text_message(str(target_chat.external_id), str(announcement.content))
            log.i(f"Purchase notification sent to user {record.user_id.hex} on {target_chat.chat_type.value}")
        except Exception as e:
            log.e(f"Failed to send purchase notification to user {record.user_id.hex}", e)
