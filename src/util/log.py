import json
import os
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from util.config import config
from util.errors import ServiceError


def _scrub_secrets(text: str) -> str:
    for secret in config.all_secrets():
        value = secret.get_secret_value()
        if value:
            text = text.replace(value, "****")
    return text


def _should_log(level: str) -> bool:
    if config.log_level == "local":
        return True  # we always log in local context
    levels = {"trace": 0, "debug": 1, "info": 2, "warning": 3, "error": 4}
    current_level = levels.get(config.log_level, 2)  # default to info
    request_level = levels.get(level.lower(), 2)
    return request_level >= current_level


def _format_args(*args: Any) -> tuple[str, list[Exception]]:
    exceptions = []
    formatted_parts = []

    # prepare the print components
    for arg in args:
        if isinstance(arg, ServiceError):
            exceptions.append(arg)
            formatted_parts.append(arg.to_log_string())
        elif isinstance(arg, Exception):
            exceptions.append(arg)
            formatted_parts.append(f"! {str(type(arg).__name__)} (see below)")
        elif hasattr(arg, "__dict__"):
            formatted_parts.append(f"{type(arg).__name__}:\n```\n{repr(arg)}\n```")
        else:
            formatted_parts.append(f"{str(arg)}")

    # edge: no message to print
    if not formatted_parts:
        return "", exceptions

    # edge: only one message line to print
    if len(formatted_parts) == 1:
        return formatted_parts[0], exceptions

    # edge: message lines are available, but no exceptions
    if not exceptions:
        head_lines = "\n ├─ ".join(formatted_parts[:-1])
        tail_line = formatted_parts[-1]
        return f"{head_lines}\n └─ {tail_line}", exceptions

    # message and exceptions are available, connect messages with a tree
    return "\n ├─ ".join(formatted_parts), exceptions


def _structured_record(level: str, message: str, exceptions: list[Exception]) -> str:
    record: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "ERROR" if exceptions else level,
        "message": _scrub_secrets(message),
        "logger": "application",
        "service.name": os.getenv("OTEL_SERVICE_NAME", "the-agent"),
        "service.version": config.version,
    }

    if exceptions:
        record["exceptions"] = [
            {
                "type": type(exception).__name__,
                "message": _scrub_secrets(str(exception)),
                "stacktrace": _scrub_secrets("".join(traceback.format_exception(exception)).strip()),
            }
            for exception in exceptions
        ]

    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        record["trace_id"] = format(span_context.trace_id, "032x")
        record["span_id"] = format(span_context.span_id, "016x")

    return json.dumps(record, ensure_ascii = False, separators = (",", ":"))


def _log_message(level: str, message: str, exceptions: list[Exception]):
    if not _should_log(level) and not exceptions:
        return

    message = _scrub_secrets(message)

    if config.log_level != "local":
        try:
            print(_structured_record(level, message, exceptions), flush = True)
        except Exception:
            if _should_log(level):
                print(f"[{level[0]}] {message}")
            for exception in exceptions:
                print(f" ‼  Message: {_scrub_secrets(str(exception))}", file = sys.stderr)
                if trace_value := exception.__traceback__:
                    trace_lines = traceback.format_tb(trace_value)
                    indented_trace = "".join(trace_lines).strip()
                    print(indented_trace, file = sys.stderr)
        return

    # for local execution, print to stdout/stderr
    print(f"[{level[0]}] {message}")
    for exception in exceptions:
        print(f" ‼  Message: {_scrub_secrets(str(exception))}", file = sys.stderr)
        if trace := exception.__traceback__:
            trace_lines = traceback.format_tb(trace)
            indented_trace = "".join(("    " + line.strip()) for line in trace_lines)
            print(indented_trace, file = sys.stderr)


def t(*args: Any):
    message, exceptions = _format_args(*args)
    _log_message("TRACE", message, exceptions)


def d(*args: Any):
    message, exceptions = _format_args(*args)
    _log_message("DEBUG", message, exceptions)


def i(*args: Any):
    message, exceptions = _format_args(*args)
    _log_message("INFO", message, exceptions)


def w(*args: Any):
    message, exceptions = _format_args(*args)
    _log_message("WARN", message, exceptions)


def e(*args: Any):
    message, exceptions = _format_args(*args)
    _log_message("ERROR", message, exceptions)
