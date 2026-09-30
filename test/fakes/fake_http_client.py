from collections import defaultdict, deque
from re import Pattern
from typing import Any

from requests import Response

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError
from util.http_client import HTTPClient


class FakeHTTPClient(HTTPClient):

    requests: list[tuple[str, dict[str, Any]]]
    responses: dict[str | Pattern[str], deque[Response | Exception]]
    post_requests: list[tuple[str, dict[str, Any]]]
    post_responses: dict[str, deque[Response | Exception]]

    def __init__(self):
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.responses = defaultdict(deque)
        self.post_requests = []
        self.post_responses = defaultdict(deque)

    def get(self, url: str, **kwargs: Any) -> Response:
        self.requests.append((url, kwargs))
        key = next((key for key in self.responses if isinstance(key, Pattern) and key.fullmatch(url)), url)
        responses = self.responses[url] if url in self.responses else self.responses[key]
        if not responses:
            raise InternalError(f"No HTTP response configured for GET {url}", DI_DEPENDENCY_NOT_MET)
        response = responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url: str, **kwargs: Any) -> Response:
        self.post_requests.append((url, kwargs))
        responses = self.post_responses[url]
        if not responses:
            raise InternalError(f"No HTTP response configured for POST {url}", DI_DEPENDENCY_NOT_MET)
        response = responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response
