from datetime import datetime
from urllib.parse import urlparse

from dateutil.relativedelta import relativedelta

from di.di import DI
from features.web_browsing.uri_cleanup import simplify_url
from util import log
from util.errors import ExternalServiceError

SOURCE_VALIDITY_MONTHS = 4


def format_sources_from_perplexity(additional_kwargs: dict, di: DI) -> str:
    search_results: list = additional_kwargs.get("search_results") or []
    citations: list = additional_kwargs.get("citations") or []

    raw_sources: list[tuple[str, str]] = []
    if search_results:
        for result in search_results:
            url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)
            if url:
                domain = urlparse(url).netloc or simplify_url(url)
                raw_sources.append((domain, simplify_url(url, strip_subdomains = False)))
    else:
        for url in citations:
            if url:
                url = str(url)
                domain = urlparse(url).netloc or simplify_url(url)
                raw_sources.append((domain, simplify_url(url, strip_subdomains = False)))

    return __render_sources(raw_sources, di)


def format_sources_from_google(grounding_chunks: list, di: DI) -> str:
    raw_sources: list[tuple[str, str]] = []
    for chunk in grounding_chunks:
        web = getattr(chunk, "web", None)
        if web:
            title = getattr(web, "title", None) or ""
            uri = getattr(web, "uri", None) or ""
            if uri:
                raw_sources.append((title, uri))
    return __render_sources(raw_sources, di)


def __render_sources(raw_sources: list[tuple[str, str]], di: DI) -> str:
    if not raw_sources:
        return ""

    cache: dict[str, str] = {}
    valid_until = datetime.now() + relativedelta(months = SOURCE_VALIDITY_MONTHS)
    lines: list[str] = []
    seen: set[str] = set()

    for domain, url in raw_sources:
        if url in seen:
            continue
        seen.add(url)

        short_url = cache.get(url)
        if short_url is None:
            try:
                short_url = di.url_shortener(url, valid_until = valid_until).execute()
                cache[url] = short_url
            except ExternalServiceError:
                log.w(f"Failed to shorten source URL, using raw: {url}")
                short_url = url
                cache[url] = short_url

        lines.append(f"- [{domain}]({short_url})")

    if not lines:
        return ""
    return "\n\nSources:\n" + "\n".join(lines)
