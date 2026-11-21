from datetime import timedelta
from re import compile

from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from util.config import config

_MAX_VERSION_BYTES = 1024
_CACHE_TTL = timedelta(hours = 1)
_NUMBER = r"(?:0|[1-9][0-9]*)"
_PRERELEASE_ID = rf"(?:{_NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BUILD_ID = r"[0-9A-Za-z-]+"
_SEMVER = compile(
    rf"{_NUMBER}\.{_NUMBER}\.{_NUMBER}"
    rf"(?:-{_PRERELEASE_ID}(?:\.{_PRERELEASE_ID})*)?"
    rf"(?:\+{_BUILD_ID}(?:\.{_BUILD_ID})*)?",
)


class CliVersionService:

    _di: DI

    def __init__(self, di: DI):
        self._di = di

    def get_version(self) -> str | None:
        url = config.cli_version_url.strip()
        if not url:
            return None

        key = ToolsCache.create_key("cli-version", url)
        try:
            cached = self._di.tools_cache_repo.get(key)
            if cached is not None and cached.expires_at is not None and not cached.is_expired():
                version = self._normalize(cached.value)
                if version is not None:
                    return version

            version = self._fetch_version(url)
            if version is None:
                return None

            entry = ToolsCache(key = key, value = version)
            entry.expires_at = entry.created_at + _CACHE_TTL
            self._di.tools_cache_repo.save(entry)
            return version
        except SQLAlchemyError:
            self._di.rollback_db_session()
            return None

    def _fetch_version(self, url: str) -> str | None:
        try:
            with self._di.http_client().get(
                url,
                stream = True,
                allow_redirects = False,
                timeout = 2,
                # suppress Requests' implicit netrc and URL credentials
                auth = lambda request: request,
            ) as response:
                if response.status_code != 200:
                    return None

                body = bytearray()
                for chunk in response.iter_content(chunk_size = _MAX_VERSION_BYTES):
                    if len(body) + len(chunk) > _MAX_VERSION_BYTES:
                        return None
                    body.extend(chunk)
                return self._normalize(body.decode("ascii"))
        except (RequestException, UnicodeDecodeError):
            return None

    @staticmethod
    def _normalize(value: str) -> str | None:
        version = value.strip().removeprefix("v")
        return version if _SEMVER.fullmatch(version) else None
