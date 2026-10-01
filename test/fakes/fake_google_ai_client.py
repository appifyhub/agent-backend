from collections import deque
from typing import Any

from google.genai.types import GenerateContentResponse, Model

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeGoogleModels:

    responses: deque[GenerateContentResponse | Exception]
    requests: list[dict[str, Any]]
    catalog: dict[str, Model]

    def __init__(self):
        self.responses = deque()
        self.requests = []
        self.catalog = {}

    def generate_content(self, **kwargs: Any) -> GenerateContentResponse:
        self.requests.append(kwargs)
        if not self.responses:
            raise InternalError("No Google response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep = True)

    def get(self, *, model: str) -> Model:
        if model not in self.catalog:
            raise InternalError(f"No Google model configured: {model}", DI_DEPENDENCY_NOT_MET)
        return self.catalog[model].model_copy(deep = True)


class FakeGoogleAIClient:

    models: FakeGoogleModels
    vertexai: bool = False

    def __init__(self):
        self.models = FakeGoogleModels()
