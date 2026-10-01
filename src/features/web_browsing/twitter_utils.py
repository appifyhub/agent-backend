import requests

from features.web_browsing.uri_cleanup import simplify_url
from util import log
from util.config import config
from util.http_client import HTTPClient


def resolve_tweet_id(url: str, http_client: HTTPClient = requests) -> str | None:
    try:
        simple_url = simplify_url(url)
        simple_domain = simple_url.split("/")[0]
        shorteners = ["t.co", "x.co", "bit.ly", "tinyurl.com", "ow.ly", "buff.ly"]
        # follow redirects and unfurl first (if needed)
        if any(simple_domain == shortener for shortener in shorteners):
            simple_url = simplify_url(http_client.get(url, timeout = config.web_timeout_s).url)
        if simple_url.startswith("twitter.com") or simple_url.startswith("x.com"):
            parts = simple_url.split("/")
            if len(parts) > 3 and parts[2] == "status":
                return parts[3].split("?")[0]
    except Exception as e:
        log.e("Error resolving tweet ID", e)
        return None
