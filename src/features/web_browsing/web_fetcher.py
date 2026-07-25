import json
import platform
import time
from datetime import datetime, timedelta
from typing import Any

import requests
from requests.exceptions import RequestException, Timeout

from di.di import DI
from features.external_tools.intelligence_presets import default_tool_for
from features.tools_cache.tools_cache import ToolsCache
from features.web_browsing.twitter_status_fetcher import TwitterStatusFetcher
from features.web_browsing.twitter_utils import resolve_tweet_id
from features.web_browsing.uri_cleanup import simplify_url
from util import log
from util.config import config

PLATFORM = f"{platform.python_implementation()}/{platform.python_version()}"
USER_AGENT = f"Mozilla/5.0 (compatible; TheAgent/1.0; {PLATFORM})"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
CACHE_PREFIX = "web-fetcher"
DEFAULT_CACHE_TTL_HTML = timedelta(weeks = 3)
DEFAULT_CACHE_TTL_JSON = timedelta(minutes = 5)


class WebFetcher:

    url: str
    html: str | None
    json: dict | None
    status_code: int | None
    error_json: dict[str, Any] | None
    __made_request: bool
    __tweet_id: str | None
    __cache_key: str
    __headers: dict[str, str]
    __params: dict[str, Any]
    __cache_ttl_html: timedelta
    __cache_ttl_json: timedelta
    __force: bool
    __tweet_fetcher: TwitterStatusFetcher | None
    __di: DI

    def __init__(
        self,
        url: str,
        di: DI,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cache_ttl_html: timedelta | None = None,
        cache_ttl_json: timedelta | None = None,
        auto_fetch_html: bool = False,
        auto_fetch_json: bool = False,
        force: bool = False,
    ):
        self.url = url
        self.__di = di
        self.html = None
        self.json = None
        self.__made_request = False
        self.status_code = None
        self.error_json = None
        self.__headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.__params = params or {}
        self.__cache_key = self.__generate_cache_key()
        self.__cache_ttl_html = cache_ttl_html or DEFAULT_CACHE_TTL_HTML
        self.__cache_ttl_json = cache_ttl_json or DEFAULT_CACHE_TTL_JSON
        self.__force = force
        self.__tweet_id = resolve_tweet_id(self.url)
        if self.__tweet_id:
            log.t(f"Resolved tweet ID: {self.__tweet_id}")
            x_api_tool = di.tool_choice_resolver.require_tool(
                TwitterStatusFetcher.TWITTER_TOOL_TYPE,
                default_tool_for(TwitterStatusFetcher.TWITTER_TOOL_TYPE),
            )
            vision_tool = di.tool_choice_resolver.require_tool(
                TwitterStatusFetcher.VISION_TOOL_TYPE,
                default_tool_for(TwitterStatusFetcher.VISION_TOOL_TYPE),
            )
            self.__tweet_fetcher = di.twitter_status_fetcher(
                self.__tweet_id, x_api_tool, vision_tool,
            )
        else:
            self.__tweet_fetcher = None
        if auto_fetch_html:
            self.fetch_html()
        if auto_fetch_json:
            self.fetch_json()

    def __generate_cache_key(self) -> str:
        headers_str = json.dumps(self.__headers, sort_keys = True)
        params_str = json.dumps(self.__params, sort_keys = True)
        key_components = f"{simplify_url(self.url)}|{headers_str}|{params_str}"
        return ToolsCache.create_key(CACHE_PREFIX, key_components)

    @property
    def made_request(self) -> bool:
        return self.__made_request

    def fetch_html(self) -> str | None:
        self.html = None  # reset value
        self.__made_request = False
        self.status_code = None

        if not self.__force:
            cache_entry = self.__di.tools_cache_repo.get(self.__cache_key)
            if cache_entry:
                if not cache_entry.is_expired():
                    log.t(f"Cache hit for '{self.__cache_key}'")
                    self.html = cache_entry.value
                    return self.html
                log.t(f"Cache expired for '{self.__cache_key}'")
            log.t(f"Cache miss for '{self.__cache_key}'")
        else:
            log.t(f"Skipping cache read for forced fetch of '{self.__cache_key}'")

        attempts = 0
        for _ in range(config.web_retries):
            try:
                self.__made_request = True
                if self.__tweet_fetcher:
                    response_text = self.__tweet_fetcher.execute()
                    self.html = f"<html><body>\n<p>\n{response_text}\n</p>\n</body></html>"
                else:
                    # run a standard request for a web page
                    response = requests.get(
                        self.url,
                        headers = self.__headers,
                        params = self.__params,
                        timeout = config.web_timeout_s,
                    )
                    self.status_code = response.status_code
                    response.raise_for_status()
                    # we need to check for binary content before caching
                    content_bytes = response.content
                    try:
                        content_text = content_bytes.decode(response.encoding or "utf-8")
                    except Exception:
                        log.w(f"Failed to decode content from {self.url}")
                        content_text = None
                    if b"\x00" in content_bytes or content_text is None:
                        log.w(f"Not caching binary or invalid content from {self.url}")
                        self.html = None
                        break
                    self.html = content_text
                self.__di.tools_cache_repo.save(
                    ToolsCache(
                        key = self.__cache_key,
                        value = self.html or "",
                        expires_at = datetime.now() + self.__cache_ttl_html,
                    ),
                )
                break
            except (RequestException, Timeout) as e:
                attempts += 1
                attempts_left = config.web_retries - attempts + 1
                log.w(f"Error fetching HTML content: {e}. Retries left: {attempts_left}")
                time.sleep(config.web_retry_delay_s)
        return self.html

    def fetch_json(self) -> dict | None:
        self.json = None  # reset value
        self.__made_request = False
        self.status_code = None
        self.error_json = None

        if not self.__force:
            cache_entry = self.__di.tools_cache_repo.get(self.__cache_key)
            if cache_entry:
                if not cache_entry.is_expired():
                    log.t(f"Cache hit for '{self.__cache_key}'")
                    self.json = json.loads(cache_entry.value)
                    return self.json
                log.t(f"Cache expired for '{self.__cache_key}'")
            log.t(f"Cache miss for '{self.__cache_key}'")
        else:
            log.t(f"Skipping cache read for forced fetch of '{self.__cache_key}'")

        attempts = 0
        for _ in range(config.web_retries):
            try:
                self.__made_request = True
                if self.__tweet_fetcher:
                    response_text = self.__tweet_fetcher.execute()
                    self.json = {"content": response_text}
                else:
                    response = requests.get(
                        self.url,
                        headers = self.__headers,
                        params = self.__params,
                        timeout = config.web_timeout_s,
                    )
                    self.status_code = response.status_code
                    if not response.ok:
                        response_json = response.json()
                        self.error_json = response_json if isinstance(response_json, dict) else None
                    response.raise_for_status()
                    self.json = response.json()
                self.__di.tools_cache_repo.save(
                    ToolsCache(
                        key = self.__cache_key,
                        value = json.dumps(self.json),
                        expires_at = datetime.now() + self.__cache_ttl_json,
                    ),
                )
                break
            except (RequestException, Timeout) as e:
                attempts += 1
                attempts_left = config.web_retries - attempts + 1
                log.w(f"Error fetching JSON content: {e}. Retries left: {attempts_left}")
                time.sleep(config.web_retry_delay_s)
        return self.json
