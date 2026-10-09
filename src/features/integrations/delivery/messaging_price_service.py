from decimal import ROUND_CEILING, Decimal
from re import sub
from typing import Any, Literal

import yaml

from db.model.chat_config import ChatConfigDB
from util.config import config

type CommsCategory = Literal["service", "utility", "marketing", "authentication"]


class MessagingPriceService:

    __platforms: dict[str, Any]

    def __init__(self):
        with open(config.integration_delivery_pricing_config_path) as f:
            self.__platforms = yaml.safe_load(f)["platforms"]

    def get(self, platform: ChatConfigDB.ChatType, recipient_id: str, category: CommsCategory = "service") -> float:
        markets = self.__platforms[platform.value]["markets"]
        digits = sub(r"\D", "", recipient_id)
        market_key = None
        default_key = None
        best_prefix_length = -1

        for key, market in markets.items():
            if market.get("default", False):
                default_key = key
            for prefix in market.get("prefixes", []):
                if digits.startswith(prefix) and len(prefix) > best_prefix_length:
                    market_key = key
                    best_prefix_length = len(prefix)

        selected_key = market_key if market_key is not None else default_key
        cost = markets[selected_key]["categories"][category.strip().lower()]
        return float(Decimal(str(cost)).quantize(Decimal("0.1"), rounding = ROUND_CEILING))
