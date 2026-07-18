import hashlib
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import SecretStr

from util import log
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, LLM_UNEXPECTED_RESPONSE
from util.errors import ExternalServiceError


def generate_short_uuid() -> str:
    return uuid4().hex[:8]


def generate_deterministic_short_uuid(seed: str) -> str:
    # noinspection InsecureHash
    hash_digest = hashlib.sha256(seed.encode()).hexdigest()
    return hash_digest[:8]


def silent(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception:
            return None

    return wrapper


def detect_image_format(content: bytes) -> str | None:
    if len(content) < 8:
        return None
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if content[:2] == b"BM":
        return "bmp"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    return None


def mask_secret(secret: str | SecretStr | None = None, mask: str = "*") -> str | None:
    if secret is None:
        return None
    # extract the secret value
    if isinstance(secret, SecretStr):
        secret = secret.get_secret_value()
    # short strings: mask all
    if len(secret) <= 4:
        return mask * len(secret)
    # medium strings: show one char on each side
    if len(secret) <= 8:
        return secret[0] + (mask * (len(secret) - 2)) + secret[-1:]
    # long strings: show 3 chars on each end with 5 masks in the middle
    return secret[:3] + (mask * 5) + secret[-3:]


def digest_md5(content: str) -> str:
    # noinspection InsecureHash
    hash_object = hashlib.md5()
    hash_object.update(content.encode("utf-8"))
    return hash_object.hexdigest()


def normalize_phone_number(phone: str | None) -> str | None:
    if phone is None:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def normalize_username(username: str | None) -> str | None:
    if username is None:
        return None
    return username.replace("@", "").replace("+", "").replace(" ", "").strip()


def extract_url_from_replicate_result(prediction: Any) -> str:
    result = prediction.output

    if not result:
        error_detail = str(prediction.error or prediction.logs or "unknown")
        status = prediction.status or "unknown"
        raise ExternalServiceError(
            f"Replicate returned empty result (status = ```{status}```, detail = ```{error_detail})```",
            EXTERNAL_EMPTY_RESPONSE,
        )

    if isinstance(result, list):
        first_item = result[0]
        if hasattr(first_item, "url"):
            return first_item.url
        elif isinstance(first_item, str):
            return first_item
        raise ExternalServiceError(f"Unexpected result type in list: {type(first_item)}", EXTERNAL_EMPTY_RESPONSE)
    elif hasattr(result, "url"):
        return result.url  # type: ignore
    elif isinstance(result, str):
        return result
    raise ExternalServiceError(f"Unexpected result type from Replicate: {type(result)}", EXTERNAL_EMPTY_RESPONSE)


def delete_file_safe(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok = True)
    except Exception as e:
        log.w(f"Failed to delete temp file {path}", e)


def parse_ai_message_content_blocks(
    message: BaseMessage,
    include_thinking: bool = False,
) -> list[str]:
    if not isinstance(message, AIMessage):
        raise ExternalServiceError(f"Received a non-AI message from LLM: {message}", LLM_UNEXPECTED_RESPONSE)

    content = message.content
    if isinstance(content, str):
        return [content] if content else []
    if not isinstance(content, list):
        raise ExternalServiceError(f"Received unexpected content from LLM: {message}", LLM_UNEXPECTED_RESPONSE)

    parsed_blocks: list[str] = []
    for block in content:
        if isinstance(block, str):
            parsed_blocks.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parsed_blocks.append(block.get("text", ""))
        elif include_thinking and isinstance(block, dict) and block.get("type") == "thinking":
            thinking = block.get("thinking", "")
            if thinking:
                lines = "\n".join(f"> {line}" for line in thinking.splitlines())
                parsed_blocks.append(f"💭\n{lines}")
        elif include_thinking and isinstance(block, dict) and block.get("type") != "redacted_thinking":
            parsed_blocks.append("\n".join(f"{key}: {value}" for key, value in block.items()))

    return [block for block in parsed_blocks if block]


def parse_ai_message_content(message: BaseMessage) -> str:
    full_text = "\n".join(parse_ai_message_content_blocks(message)).strip()
    if not full_text:
        raise ExternalServiceError(f"Received empty content from LLM: {message}", LLM_UNEXPECTED_RESPONSE)
    return full_text


def parse_gumroad_form(form_dict: dict[str, str]) -> dict[str, Any]:
    url_params = {}
    custom_fields = {}
    keys_to_remove = []

    for key, value in form_dict.items():
        if key.startswith("url_params[") and key.endswith("]"):
            param_name = key[11:-1]
            url_params[param_name] = value
            keys_to_remove.append(key)
        elif key.startswith("custom_fields[") and key.endswith("]"):
            field_name = key[14:-1]
            custom_fields[field_name] = value
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del form_dict[key]

    if url_params:
        form_dict["url_params"] = url_params  # type: ignore
    if custom_fields:
        form_dict["custom_fields"] = custom_fields  # type: ignore

    return form_dict
