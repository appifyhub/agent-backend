from typing import Any, Protocol

from requests import Response


class HTTPClient(Protocol):

    def get(self, url: str, **kwargs: Any) -> Response: ...
