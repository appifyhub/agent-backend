from util.errors import ExternalServiceError


class FakeUrlShortener:

    short_url: str
    error: ExternalServiceError | None
    executions: int
    requested_urls: list[str]

    def __init__(self, short_url: str):
        self.short_url = short_url
        self.error = None
        self.executions = 0
        self.requested_urls = []

    def for_url(self, long_url: str) -> "FakeUrlShortener":
        self.requested_urls.append(long_url)
        return self

    def execute(self) -> str:
        self.executions += 1
        if self.error is not None:
            raise self.error
        return self.short_url
