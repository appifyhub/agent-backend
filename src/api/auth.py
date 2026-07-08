import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, jwt
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from util import log
from util.config import config
from util.error_codes import EMPTY_TOKEN, INVALID_RESOURCE_TOKEN, NO_USER_ID_IN_TOKEN
from util.errors import AuthenticationError

__CLAIM_CHAT_ID = "chat_id"
__CLAIM_ATTACHMENT_ID = "attachment_id"
__CLAIM_ISSUER_USER_ID = "issuer_user_id"
__JWT_ALGORITHM = "HS256"

api_key_header = APIKeyHeader(name = "X-API-Key", auto_error = True)
telegram_auth_key_header = APIKeyHeader(name = "X-Telegram-Bot-Api-Secret-Token", auto_error = False)
jwt_header = HTTPBearer(bearerFormat = "JWT", auto_error = True)


@dataclass(frozen = True)
class PublicAttachmentTokenClaims:
    chat_id: str
    attachment_id: str
    issuer_user_id: str


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != config.api_key.get_secret_value():
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Could not validate the API key")
    return api_key


def verify_telegram_auth_key(auth_key: str = Security(telegram_auth_key_header)) -> str:
    if config.telegram_must_auth and auth_key != config.telegram_auth_key.get_secret_value():
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Could not validate the Telegram auth token")
    return auth_key


def verify_whatsapp_webhook_challenge(mode: str, challenge: str, verify_token: str) -> str:
    if not config.whatsapp_must_auth:
        log.i("WhatsApp webhook verification skipped (auth disabled)")
        return challenge
    token_valid = verify_token == config.whatsapp_auth_key.get_secret_value()
    if mode == "subscribe" and token_valid:
        log.i("WhatsApp webhook verified successfully")
        return challenge
    else:
        log.w(f"WhatsApp webhook verification failed: mode={mode}, token_match={token_valid}")
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Webhook verification failed")


def verify_whatsapp_signature(payload: bytes, signature_header: str | None) -> None:
    if not config.whatsapp_must_auth:
        log.i("WhatsApp signature verification skipped (auth disabled)")
        return
    if not signature_header:
        log.w("WhatsApp signature verification failed: missing X-Hub-Signature-256 header")
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Missing signature header")
    if not signature_header.startswith("sha256="):
        log.w(f"WhatsApp signature verification failed: invalid header format: {signature_header}")
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Invalid signature format")
    received_signature = signature_header[7:]
    expected_signature = hmac.new(config.whatsapp_app_secret.get_secret_value().encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, received_signature):
        log.w("WhatsApp signature verification failed: signature mismatch")
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Invalid signature")
    log.i("WhatsApp signature verified successfully")


def verify_gumroad_auth_key(auth_key: str) -> None:
    if not config.gumroad_must_auth:
        log.i("Gumroad auth verification skipped (auth disabled)")
        return
    if auth_key != config.gumroad_auth_key.get_secret_value():
        log.w("Gumroad auth verification failed: token mismatch")
        raise HTTPException(status_code = HTTP_403_FORBIDDEN, detail = "Invalid auth token")
    log.i("Gumroad auth verified successfully")


def verify_jwt_credentials(authorization: HTTPAuthorizationCredentials = Security(jwt_header)) -> Dict[str, Any]:
    try:
        return verify_jwt_token(authorization.credentials)
    except ExpiredSignatureError as e:
        message = "Token has expired"
        log.w(message, e)
        raise HTTPException(
            status_code = HTTP_401_UNAUTHORIZED,
            detail = message,
            headers = {"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        message = "Could not validate access credentials"
        log.w(message, e)
        raise HTTPException(
            status_code = HTTP_401_UNAUTHORIZED,
            detail = message,
            headers = {"WWW-Authenticate": "Bearer"},
        )


def verify_jwt_token(token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        config.jwt_secret_key.get_secret_value(),
        algorithms = [__JWT_ALGORITHM],
        options = {"verify_aud": False},
    )


def get_user_id_from_jwt(token_claims: Dict[str, Any] | None) -> str:
    if not token_claims:
        raise AuthenticationError("Empty token", EMPTY_TOKEN)
    user_id = token_claims.get("sub")
    if not user_id:
        raise AuthenticationError("No user ID in token", NO_USER_ID_IN_TOKEN)
    return user_id


def get_chat_type_from_jwt(token_claims: Dict[str, Any] | None) -> str | None:
    if not token_claims:
        return None
    return token_claims.get("platform")


def create_jwt_token(payload: Dict[str, Any], expires_in: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = payload.copy()
    to_encode.update(
        {
            "exp": now + expires_in,
            "iat": now,
            "version": config.version,
        },
    )
    encoded_jwt = jwt.encode(to_encode, config.jwt_secret_key.get_secret_value(), algorithm = __JWT_ALGORITHM)
    return encoded_jwt


def create_public_attachment_token(chat_id: str, attachment_id: str, issuer_user_id: str, ttl_seconds: int) -> str:
    return create_jwt_token(
        {
            __CLAIM_CHAT_ID: chat_id,
            __CLAIM_ATTACHMENT_ID: attachment_id,
            __CLAIM_ISSUER_USER_ID: issuer_user_id,
        },
        timedelta(seconds = ttl_seconds),
    )


def verify_public_attachment_token(token: str) -> PublicAttachmentTokenClaims:
    try:
        claims = verify_jwt_token(token)
    except ExpiredSignatureError as e:
        raise AuthenticationError("Public attachment token expired", INVALID_RESOURCE_TOKEN) from e
    except Exception as e:
        raise AuthenticationError("Invalid public attachment token", INVALID_RESOURCE_TOKEN) from e

    chat_id = claims.get(__CLAIM_CHAT_ID)
    if not chat_id:
        raise AuthenticationError("Public attachment token is missing chat ID", INVALID_RESOURCE_TOKEN)
    attachment_id = claims.get(__CLAIM_ATTACHMENT_ID)
    if not attachment_id:
        raise AuthenticationError("Public attachment token is missing attachment ID", INVALID_RESOURCE_TOKEN)
    issuer_user_id = claims.get(__CLAIM_ISSUER_USER_ID)
    if not issuer_user_id:
        raise AuthenticationError("Public attachment token is missing issuer user ID", INVALID_RESOURCE_TOKEN)

    return PublicAttachmentTokenClaims(
        chat_id = str(chat_id),
        attachment_id = str(attachment_id),
        issuer_user_id = str(issuer_user_id),
    )
