from pathlib import Path

import requests

from util import log
from util.config import config
from util.error_codes import WEB_FETCH_FAILED
from util.errors import ExternalServiceError


class PhotoDownloader:

    __bearer_token: str | None

    def __init__(self, bearer_token: str | None = None):
        self.__bearer_token = bearer_token

    def download(self, url: str) -> bytes | None:
        try:
            headers = {"User-Agent": config.user_agent}
            if self.__bearer_token:
                headers["Authorization"] = f"Bearer {self.__bearer_token}"
            response = requests.get(url, headers = headers, timeout = config.web_timeout_s)
            response.raise_for_status()
            return response.content
        except Exception as e:
            log.w(f"Failed to download photo from {url}", e)
            return None

    def download_to(self, url: str, destination: Path) -> bool:
        try:
            headers = {"User-Agent": config.user_agent}
            if self.__bearer_token:
                headers["Authorization"] = f"Bearer {self.__bearer_token}"
            with requests.get(
                url,
                headers = headers,
                timeout = config.web_timeout_s,
                stream = True,
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_content(chunk_size = 1024 * 256):
                        if chunk:
                            output.write(chunk)
            if destination.stat().st_size == 0:
                destination.unlink(missing_ok = True)
                return False
            return True
        except Exception as e:
            destination.unlink(missing_ok = True)
            log.w(f"Failed to download photo from {url}", e)
            return False

    def download_many(self, urls: list[str]) -> list[bytes]:
        results = []
        for url in urls:
            data = self.download(url)
            if data:
                results.append(data)
        return results

    def require(self, url: str) -> bytes:
        data = self.download(url)
        if not data:
            raise ExternalServiceError(f"Failed to download required photo: {url}", WEB_FETCH_FAILED)
        return data
