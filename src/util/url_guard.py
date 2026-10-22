import ipaddress
import socket
import urllib.request
from contextlib import contextmanager
from http.client import HTTPResponse
from typing import Any, Generator
from urllib.parse import urljoin, urlparse

from requests import Response

from util.error_codes import WEB_FETCH_FAILED
from util.errors import ValidationError
from util.http_client import HTTPClient

__ALLOWED_SCHEMES = frozenset({"http", "https"})
__DEFAULT_PORTS = {"http": 80, "https": 443}
__REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
__MAX_REDIRECTS = 5


def validate_public_http_url(url: str) -> str:
    """Reject any fetch destination that is not a publicly routable http(s) address.

    Guards every outbound fetch driven by chat, LLM, or third-party content against
    reaching loopback, link-local (including cloud metadata), private, or reserved
    ranges. Resolution happens here, so a hostname pointing at an internal address is
    refused even though the URL itself looks public. Returns the URL for call chaining.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in __ALLOWED_SCHEMES:
        raise ValidationError(f"Refusing fetch destination with scheme '{parsed.scheme}'", WEB_FETCH_FAILED)
    if not parsed.hostname:
        raise ValidationError("Refusing fetch destination without a host", WEB_FETCH_FAILED)
    for address in __resolve(parsed.hostname, parsed.port or __DEFAULT_PORTS[scheme]):
        if not address.is_global:
            raise ValidationError(f"Refusing fetch destination '{parsed.hostname}' resolving to non-public address {address}", WEB_FETCH_FAILED)  # ruff: ignore[line-too-long]
    return url


def guarded_get(http_client: HTTPClient, url: str, **kwargs: Any) -> Response:
    """Fetch through the given client, validating the initial URL and every redirect hop.

    Redirects are followed manually because a validated public URL can redirect into an
    internal address, which would defeat a one-shot check on the original URL. The
    connect-time IP is re-validated inside the socket to close the DNS-rebinding window:
    a second DNS lookup at connect time cannot redirect the socket to a non-public address
    even if the attacker's resolver returns a different answer than the validation lookup.
    """
    current = validate_public_http_url(url)
    for _ in range(__MAX_REDIRECTS):
        with __rebind_guard():
            response = http_client.get(current, allow_redirects = False, **kwargs)
        location = response.headers.get("location") if response.status_code in __REDIRECT_STATUSES else None
        if not location:
            return response
        response.close()
        current = validate_public_http_url(urljoin(current, location))
    raise ValidationError(f"Refusing fetch after {__MAX_REDIRECTS} redirects: {url}", WEB_FETCH_FAILED)


def guarded_urlopen(url: str, timeout: float, headers: dict[str, str] | None = None) -> HTTPResponse:
    """Open a URL through urllib with the same destination guard on every redirect hop."""
    validate_public_http_url(url)
    request = urllib.request.Request(url, headers = headers or {})
    opener = urllib.request.build_opener(__GuardedRedirectHandler)
    with __rebind_guard():
        return opener.open(request, timeout = timeout)


@contextmanager
def __rebind_guard() -> Generator[None, None, None]:
    """Patch socket.create_connection for the duration of the call to re-validate the resolved IP at connect time."""
    _original = socket.create_connection

    def _checked(address, *args, **kwargs):
        host, port = address
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            # still a hostname — resolve and check; DNS rebind window is between here and the actual connect
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        if not ip.is_global:
            raise ValidationError(f"Refusing connect-time address {ip} (DNS rebinding detected)", WEB_FETCH_FAILED)
        return _original(address, *args, **kwargs)

    socket.create_connection = _checked
    try:
        yield
    finally:
        socket.create_connection = _original


class __GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def __resolve(hostname: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, port, proto = socket.IPPROTO_TCP)
    except OSError as e:
        raise ValidationError(f"Could not resolve fetch destination '{hostname}'", WEB_FETCH_FAILED) from e
    if not infos:
        raise ValidationError(f"No addresses for fetch destination '{hostname}'", WEB_FETCH_FAILED)
    return [ipaddress.ip_address(info[4][0]) for info in infos]
