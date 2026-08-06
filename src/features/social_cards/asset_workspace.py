from contextlib import AbstractContextManager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from features.web_browsing.photo_downloader import PhotoDownloader


class SocialCardAssetWorkspace(AbstractContextManager["SocialCardAssetWorkspace"]):

    __downloader: PhotoDownloader
    __temporary_directory: TemporaryDirectory[str]

    def __init__(self, downloader: PhotoDownloader):
        self.__downloader = downloader
        self.__temporary_directory = TemporaryDirectory(prefix = "social-card-")

    def __enter__(self) -> "SocialCardAssetWorkspace":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.__temporary_directory.cleanup()

    @property
    def root(self) -> Path:
        return Path(self.__temporary_directory.name)

    def new_path(self, suffix: str = "") -> Path:
        normalized_suffix = suffix if not suffix or suffix.startswith(".") else f".{suffix}"
        return self.root.joinpath(f"{uuid4().hex}{normalized_suffix}")

    def download(self, url: str) -> Path | None:
        suffix = Path(urlparse(url).path).suffix
        destination = self.new_path(suffix if len(suffix) <= 10 else "")
        return destination if self.__downloader.download_to(url, destination) else None
