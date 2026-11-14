import re
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from util.error_codes import CLI_TTL_TOO_LONG, INVALID_CLI_TTL
from util.errors import BadRequestError

DEFAULT_CLI_TOKEN_TTL = relativedelta(months = 6)
MAX_CLI_TOKEN_TTL = relativedelta(years = 2)

__TTL_PATTERN = re.compile(r"([1-9][0-9]*)(s|min|m|h|d|mo|M|y)")
__MAX_DIGITS = 9
__GRAMMAR_HINT = "a positive whole number followed by one unit: s, m (or min), h, d, mo (or M), or y, for example 12h, 30d, or 6mo"  # ruff: ignore[line-too-long]
__MAX_HINT = "The maximum is 2 years (2y, 24mo, or 730d)."


def resolve_cli_token_expiry(ttl_as_text: str | None, now: datetime) -> datetime:
    # let's validate it first
    if ttl_as_text is None:
        return now + DEFAULT_CLI_TOKEN_TTL
    match = __TTL_PATTERN.fullmatch(ttl_as_text)
    if match is None:
        raise BadRequestError(f"Invalid token lifetime. Use {__GRAMMAR_HINT}.", INVALID_CLI_TTL)
    amount_as_text, unit = match.groups()
    too_long = BadRequestError(f"Token lifetime is too long. {__MAX_HINT}", CLI_TTL_TOO_LONG)
    if len(amount_as_text) > __MAX_DIGITS:
        raise too_long

    # it's valid, let's resolve the delta
    amount = int(amount_as_text)
    try:
        expires_at = now + __resolve_delta(amount, unit)
        latest_allowed = now + MAX_CLI_TOKEN_TTL
    except (OverflowError, ValueError) as e:
        raise too_long from e

    # final check: verify that it's not too long in the future
    if expires_at > latest_allowed:
        raise too_long

    return expires_at


def __resolve_delta(amount: int, unit: str) -> timedelta | relativedelta:
    if unit == "s":
        return timedelta(seconds = amount)
    if unit in ("m", "min"):
        return timedelta(minutes = amount)
    if unit == "h":
        return timedelta(hours = amount)
    if unit == "d":
        return timedelta(days = amount)
    if unit in ("mo", "M"):
        return relativedelta(months = amount)
    return relativedelta(years = amount)
