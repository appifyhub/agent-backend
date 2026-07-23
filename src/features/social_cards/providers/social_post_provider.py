from typing import ClassVar, Protocol

from features.external_tools.external_tool import ToolType
from features.social_cards.domain import SocialPost


class SocialPostProvider(Protocol):

    tool_type: ClassVar[ToolType]

    @staticmethod
    def can_handle(url: str) -> bool:
        pass

    def fetch(self, url: str) -> SocialPost:
        pass
