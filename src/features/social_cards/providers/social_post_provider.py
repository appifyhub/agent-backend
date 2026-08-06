from typing import ClassVar, Protocol

from features.external_tools.external_tool import ToolType
from features.social_cards.social_card_models import SocialPost


class SocialPostProvider(Protocol):

    tool_type: ClassVar[ToolType]

    @staticmethod
    def can_handle(url: str) -> bool:
        pass

    def fetch(self, url: str) -> SocialPost:
        pass
