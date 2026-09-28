class FakeUrlShortener:

    short_url: str

    def __init__(self, short_url: str):
        self.short_url = short_url

    def execute(self) -> str:
        return self.short_url
