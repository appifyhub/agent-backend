from collections import defaultdict, deque
from typing import Any

from requests import Response

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError
from util.http_client import HTTPClient


class FakeHTTPClient(HTTPClient):

    requests: list[tuple[str, dict[str, Any]]]
    responses: dict[str, deque[Response | Exception]]

    def __init__(self):
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, deque[Response | Exception]] = defaultdict(deque)

    def get(self, url: str, **kwargs: Any) -> Response:
        self.requests.append((url, kwargs))
        if not self.responses[url]:
            raise InternalError(f"No HTTP response configured for GET {url}", DI_DEPENDENCY_NOT_MET)
        response = self.responses[url].popleft()
        if isinstance(response, Exception):
            raise response
        return response
