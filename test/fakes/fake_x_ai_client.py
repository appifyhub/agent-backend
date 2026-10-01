from collections import deque
from typing import Any

from xai_sdk.chat import Response
from xai_sdk.sync.image import ImageResponse

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeXAIImage:

    responses: deque[ImageResponse | Exception]
    requests: list[dict[str, Any]]

    def __init__(self):
        self.responses = deque()
        self.requests = []

    def sample(self, **kwargs: Any) -> ImageResponse:
        self.requests.append(kwargs)
        if not self.responses:
            raise InternalError("No xAI image response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class FakeXAIChat:

    responses: deque[Response | Exception]
    requests: list[dict[str, Any]]

    def __init__(self, responses: deque[Response | Exception]):
        self.responses = responses
        self.requests = []

    def sample(self, **kwargs: Any) -> Response:
        self.requests.append(kwargs)
        if not self.responses:
            raise InternalError("No xAI chat response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class FakeXAIChats:

    responses: deque[Response | Exception]
    requests: list[dict[str, Any]]
    conversations: list[FakeXAIChat]

    def __init__(self):
        self.responses = deque()
        self.requests = []
        self.conversations = []

    def create(self, **kwargs: Any) -> FakeXAIChat:
        self.requests.append(kwargs)
        chat = FakeXAIChat(self.responses)
        self.conversations.append(chat)
        return chat


class FakeXAIClient:

    image: FakeXAIImage
    chat: FakeXAIChats

    def __init__(self):
        self.image = FakeXAIImage()
        self.chat = FakeXAIChats()
