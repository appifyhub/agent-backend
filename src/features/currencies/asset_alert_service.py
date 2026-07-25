import math
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.currencies.asset_price import AssetPrice, AssetType
from features.currencies.price_alert import PriceAlert
from features.integrations.integrations import resolve_agent_user
from util import log
from util.error_codes import BOT_CANNOT_SET_ALERTS, NO_PRIVATE_CHAT
from util.errors import AuthorizationError

DATETIME_PRINT_FORMAT = "%Y-%m-%d %H:%M %Z"


class AssetAlertService:

    class TriggeredAlert(BaseModel):
        chat_id: UUID
        owner_id: UUID
        asset_type: AssetType
        asset_id: str
        currency: str
        threshold_percent: int
        old_price: float
        old_price_time: str
        new_price: float
        new_price_time: str
        price_change_percent: int

    class ActiveAlert(BaseModel):
        chat_id: UUID
        owner_id: UUID
        asset_type: AssetType
        asset_id: str
        currency: str
        threshold_percent: int
        last_price: float
        last_price_time: str

    __target_chat_config: ChatConfig | None
    __di: DI

    def __init__(
        self,
        target_chat_id: str | None,  # can be for a specific chat, or all chats
        di: DI,
    ):
        self.__di = di
        self.__target_chat_config = self.__di.authorization_service.validate_chat(target_chat_id) if target_chat_id else None

    def create_alert(
        self,
        asset: str,
        currency: str,
        threshold_percent: int,
        asset_type: str | None = None,
    ) -> ActiveAlert:
        log.d(f"Setting price alert for {asset}/{currency} at {threshold_percent}%")
        if not self.__target_chat_config:
            raise AuthorizationError("Target chat is not set", NO_PRIVATE_CHAT)
        agent_user = resolve_agent_user(ChatConfigDB.ChatType.background)
        if self.__di.invoker.id == agent_user.id:
            raise AuthorizationError("Bot cannot set price alerts", BOT_CANNOT_SET_ALERTS)

        self.__di.authorization_service.validate_chat_admin(self.__di.invoker, self.__target_chat_config)
        current_price = self.__di.asset_price_service.execute(
            asset = asset,
            currency = currency,
            asset_type = asset_type,
            force = False,
        )
        price_alert = self.__di.price_alert_repo.save(
            PriceAlert(
                chat_id = self.__target_chat_config.chat_id,
                owner_id = self.__di.invoker.id,
                asset_type = current_price.asset_type,
                asset_id = current_price.asset,
                currency = current_price.currency,
                threshold_percent = threshold_percent,
                last_price = current_price.unit_price,
                last_price_time = datetime.now(),
            ),
        )
        return self.__active_alert(price_alert)

    def delete_alert(
        self,
        asset: str,
        currency: str,
        asset_type: str | None = None,
    ) -> ActiveAlert | None:
        log.d(f"Deleting price alert for {asset}/{currency}")
        if not self.__target_chat_config:
            raise AuthorizationError("Target chat is not set", NO_PRIVATE_CHAT)

        self.__di.authorization_service.validate_chat_admin(self.__di.invoker, self.__target_chat_config)
        normalized_asset = asset.strip().upper()
        normalized_currency = currency.strip().upper()
        resolved_type = self.__di.asset_price_service.resolve_asset_type(normalized_asset, asset_type)
        deleted_alert = self.__di.price_alert_repo.delete(
            self.__target_chat_config.chat_id,
            resolved_type,
            normalized_asset,
            normalized_currency,
        )
        if deleted_alert is None and resolved_type == AssetType.stock:
            current_price = self.__di.asset_price_service.execute(
                asset = normalized_asset,
                currency = normalized_currency,
                asset_type = resolved_type.value,
                force = False,
            )
            deleted_alert = self.__di.price_alert_repo.delete(
                self.__target_chat_config.chat_id,
                current_price.asset_type,
                current_price.asset,
                current_price.currency,
            )
        return self.__active_alert(deleted_alert) if deleted_alert else None

    def get_active_alerts(self) -> list[ActiveAlert]:
        price_alerts: list[PriceAlert]
        if self.__target_chat_config:
            log.d(f"Listing price alerts for chat '{self.__target_chat_config.chat_id}'")
            price_alerts = self.__di.price_alert_repo.get_all_by_chat(self.__target_chat_config.chat_id)
        else:
            log.d("Listing all price alerts")
            price_alerts = self.__di.price_alert_repo.get_all()
        return [
            self.__active_alert(price_alert)
            for price_alert in price_alerts
        ]

    def get_triggered_alerts(self) -> list[TriggeredAlert]:
        log.d("Checking triggered price alerts")

        price_alerts: list[PriceAlert]
        if self.__target_chat_config:
            price_alerts = self.__di.price_alert_repo.get_all_by_chat(self.__target_chat_config.chat_id)
        else:
            price_alerts = self.__di.price_alert_repo.get_all()
        triggered_alerts: list[AssetAlertService.TriggeredAlert] = []
        current_prices: dict[tuple[UUID, AssetType, str, str], float] = {}
        failed_lookups: set[tuple[UUID, AssetType, str, str]] = set()
        for alert in price_alerts:
            lookup_key = (alert.owner_id, alert.asset_type, alert.asset_id, alert.currency)
            if lookup_key in failed_lookups:
                continue
            try:
                current_price = current_prices.get(lookup_key)
                if current_price is None:
                    scoped_di = self.__di.clone(invoker_id = alert.owner_id.hex, invoker_chat_id = alert.chat_id.hex)
                    asset_price: AssetPrice = scoped_di.asset_price_service.execute_normalized(
                        asset_id = alert.asset_id,
                        currency = alert.currency,
                        asset_type = alert.asset_type,
                        force = False,
                    )
                    current_price = asset_price.unit_price
                    current_prices[lookup_key] = current_price
                price_change_percent: int
                if alert.last_price == 0:
                    price_change_percent = int(math.ceil(current_price * 100))
                else:
                    change_ratio = (current_price - alert.last_price) / alert.last_price
                    price_change_percent = int(math.ceil(change_ratio * 100))

                if abs(price_change_percent) >= alert.threshold_percent:
                    last_price_time = datetime.now()
                    triggered_alerts.append(
                        AssetAlertService.TriggeredAlert(
                            chat_id = alert.chat_id,
                            owner_id = alert.owner_id,
                            asset_type = alert.asset_type,
                            asset_id = alert.asset_id,
                            currency = alert.currency,
                            threshold_percent = alert.threshold_percent,
                            old_price = alert.last_price,
                            old_price_time = alert.last_price_time.strftime(DATETIME_PRINT_FORMAT),
                            new_price = current_price,
                            new_price_time = last_price_time.strftime(DATETIME_PRINT_FORMAT),
                            price_change_percent = price_change_percent,
                        ),
                    )
                    self.__di.price_alert_repo.save(
                        replace(alert, last_price = current_price, last_price_time = last_price_time),
                    )
            except Exception as e:
                failed_lookups.add(lookup_key)
                asset_pair = f"{alert.asset_type.value}:{alert.asset_id}/{alert.currency}"
                log.w(f"Failed to check chat '{alert.chat_id}' alert '{asset_pair}'", e)
                continue
        return triggered_alerts

    @staticmethod
    def __active_alert(price_alert: PriceAlert) -> ActiveAlert:
        return AssetAlertService.ActiveAlert(
            chat_id = price_alert.chat_id,
            owner_id = price_alert.owner_id,
            asset_type = price_alert.asset_type,
            asset_id = price_alert.asset_id,
            currency = price_alert.currency,
            threshold_percent = price_alert.threshold_percent,
            last_price = price_alert.last_price,
            last_price_time = price_alert.last_price_time.strftime(DATETIME_PRINT_FORMAT),
        )
