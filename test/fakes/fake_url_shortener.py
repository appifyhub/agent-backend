from util.errors import ExternalServiceError


class FakeUrlShortener:

    short_url: str
    error: ExternalServiceError | None
    executions: int

    def __init__(self, short_url: str):
        self.short_url = short_url
        self.error = None
        self.executions = 0

    def execute(self) -> str:
        self.executions += 1
        if self.error is not None:
            raise self.error
        return self.short_url
