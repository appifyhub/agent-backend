from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import RunnableConfig
from stubs import external

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeChatModel:

    responses: deque[BaseMessage | Exception | Callable[[], BaseMessage]]
    prompts: list[list[BaseMessage]]
    invocations: list[tuple[RunnableConfig | None, dict[str, Any]]]
    _llm_type: str = "fake-chat-model"

    def __init__(self):
        self.responses = deque()
        self.prompts = []
        self.invocations = []

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self

    def invoke(
        self,
        messages: list[BaseMessage],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        self.prompts.append([message.model_copy(deep = True) for message in messages])
        self.invocations.append((config, kwargs))
        if not self.responses:
            raise InternalError("No chat model response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return response.model_copy(deep = True)

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return external.chat_result(generations = [{"message": self.invoke(messages, **kwargs)}])
