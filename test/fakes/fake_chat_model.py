from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeChatModel:

    responses: deque[BaseMessage | Exception | Callable[[], BaseMessage]]
    prompts: list[list[BaseMessage]]

    def __init__(self):
        self.responses = deque()
        self.prompts = []

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self

    def invoke(
        self,
        messages: list[BaseMessage],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        self.prompts.append([message.model_copy(deep = True) for message in messages])
        if not self.responses:
            raise InternalError("No chat model response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return response.model_copy(deep = True)
