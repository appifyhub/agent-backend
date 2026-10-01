from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from hmac import HMAC
from unittest import TestCase

import stubs
from fastapi import HTTPException
from jose import jwt
from pydantic import SecretStr
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from api.auth import (
    create_jwt_token,
    create_public_attachment_token,
    get_chat_type_from_jwt,
    get_user_id_from_jwt,
    verify_api_key,
    verify_gumroad_auth_key,
    verify_jwt_credentials,
    verify_jwt_token,
    verify_public_attachment_token,
    verify_telegram_auth_key,
    verify_whatsapp_signature,
    verify_whatsapp_webhook_challenge,
)
from util.config import config
from util.error_codes import EMPTY_TOKEN, INVALID_RESOURCE_TOKEN, NO_USER_ID_IN_TOKEN
from util.errors import AuthenticationError


class AuthTest(TestCase):

    def test_missing_api_key(self):
        with self.assertRaises(HTTPException) as context:
            # server will break the rule too, so:
            # noinspection PyTypeChecker
            verify_api_key(None)
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Could not validate the API key")

    def test_invalid_api_key(self):
        with self.assertRaises(HTTPException) as context:
            verify_api_key("NOTA-VALI-DKEY")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Could not validate the API key")

    def test_valid_api_key(self):
        self.addCleanup(setattr, config, "api_key", config.api_key)
        config.api_key = SecretStr("VALI-DKEY")
        api_key = verify_api_key("VALI-DKEY")
        self.assertEqual(api_key, "VALI-DKEY")

    def test_missing_telegram_auth_key(self):
        self.addCleanup(setattr, config, "telegram_must_auth", config.telegram_must_auth)
        config.telegram_must_auth = True
        with self.assertRaises(HTTPException) as context:
            # server will break the rule too, so:
            # noinspection PyTypeChecker
            verify_telegram_auth_key(None)
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Could not validate the Telegram auth token")

    def test_invalid_telegram_auth_key(self):
        self.addCleanup(setattr, config, "telegram_must_auth", config.telegram_must_auth)
        config.telegram_must_auth = True
        with self.assertRaises(HTTPException) as context:
            verify_telegram_auth_key("NOTA-VALI-DKEY")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Could not validate the Telegram auth token")

    def test_disabled_telegram_auth_key(self):
        self.addCleanup(setattr, config, "telegram_must_auth", config.telegram_must_auth)
        config.telegram_must_auth = False
        auth_key = verify_telegram_auth_key("")
        self.assertEqual(auth_key, "")

    def test_valid_telegram_auth_key(self):
        self.addCleanup(setattr, config, "telegram_must_auth", config.telegram_must_auth)
        config.telegram_must_auth = True
        self.addCleanup(setattr, config, "telegram_auth_key", config.telegram_auth_key)
        config.telegram_auth_key = SecretStr("VALI-DKEY")
        auth_key = verify_telegram_auth_key("VALI-DKEY")
        self.assertEqual(auth_key, "VALI-DKEY")

    def test_missing_jwt_token(self):
        with self.assertRaises(HTTPException) as context:
            # noinspection PyTypeChecker
            verify_jwt_credentials(None)
        self.assertEqual(context.exception.status_code, HTTP_401_UNAUTHORIZED)
        self.assertEqual(context.exception.detail, "Could not validate access credentials")

    def test_invalid_jwt_token(self):
        with self.assertRaises(HTTPException) as context:
            verify_jwt_credentials(stubs.external.http_authorization_credentials(credentials = "invalid-token"))
        self.assertEqual(context.exception.status_code, HTTP_401_UNAUTHORIZED)
        self.assertEqual(context.exception.detail, "Could not validate access credentials")

    def test_valid_jwt_token(self):
        payload = stubs.api.jwt_claims()
        token = create_jwt_token(payload, expires_in = timedelta(minutes = 1))

        result = verify_jwt_credentials(stubs.external.http_authorization_credentials(credentials = token))

        self.assertEqual(result["sub"], payload["sub"])
        self.assertEqual(result["platform"], payload["platform"])

    def test_create_jwt_token(self):
        payload = stubs.api.jwt_claims()
        encoded_token = create_jwt_token(payload, expires_in = timedelta(minutes = 1))
        decoded_token = jwt.decode(encoded_token, config.jwt_secret_key.get_secret_value(), algorithms = ["HS256"])
        self.assertIsInstance(encoded_token, str)
        self.assertEqual(decoded_token["sub"], payload["sub"])
        self.assertEqual(decoded_token["platform"], payload["platform"])
        self.assertEqual(decoded_token["exp"] - decoded_token["iat"], 60)
        self.assertEqual(decoded_token["version"], config.version)

    def test_create_public_attachment_token(self):
        expected = stubs.api.public_attachment_token_claims()
        encoded_token = create_public_attachment_token(
            expected.chat_id,
            expected.attachment_id,
            expected.issuer_user_id,
            ttl_seconds = 123,
        )
        decoded_token = verify_jwt_token(encoded_token)

        self.assertEqual(decoded_token["chat_id"], expected.chat_id)
        self.assertEqual(decoded_token["attachment_id"], expected.attachment_id)
        self.assertEqual(decoded_token["issuer_user_id"], expected.issuer_user_id)
        self.assertEqual(decoded_token["exp"] - decoded_token["iat"], 123)

    def test_verify_public_attachment_token(self):
        expected = stubs.api.public_attachment_token_claims()
        encoded_token = create_public_attachment_token(
            expected.chat_id,
            expected.attachment_id,
            expected.issuer_user_id,
            ttl_seconds = 123,
        )

        claims = verify_public_attachment_token(encoded_token)

        self.assertEqual(claims, expected)

    def test_verify_public_attachment_token_rejects_expired_token(self):
        encoded_token = create_jwt_token(
            asdict(stubs.api.public_attachment_token_claims()),
            timedelta(seconds = -1),
        )

        with self.assertRaises(AuthenticationError) as context:
            verify_public_attachment_token(encoded_token)

        self.assertEqual(context.exception.error_code, INVALID_RESOURCE_TOKEN)

    def test_verify_public_attachment_token_rejects_missing_attachment_id(self):
        claims = asdict(stubs.api.public_attachment_token_claims())
        claims.pop("attachment_id")
        encoded_token = create_jwt_token(
            claims,
            expires_in = timedelta(minutes = 1),
        )

        with self.assertRaises(AuthenticationError) as context:
            verify_public_attachment_token(encoded_token)

        self.assertEqual(context.exception.error_code, INVALID_RESOURCE_TOKEN)

    def test_verify_public_attachment_token_rejects_missing_chat_id(self):
        claims = asdict(stubs.api.public_attachment_token_claims())
        claims.pop("chat_id")
        encoded_token = create_jwt_token(
            claims,
            expires_in = timedelta(minutes = 1),
        )

        with self.assertRaises(AuthenticationError) as context:
            verify_public_attachment_token(encoded_token)

        self.assertEqual(context.exception.error_code, INVALID_RESOURCE_TOKEN)

    def test_verify_public_attachment_token_rejects_missing_issuer_user_id(self):
        claims = asdict(stubs.api.public_attachment_token_claims())
        claims.pop("issuer_user_id")
        encoded_token = create_jwt_token(
            claims,
            expires_in = timedelta(minutes = 1),
        )

        with self.assertRaises(AuthenticationError) as context:
            verify_public_attachment_token(encoded_token)

        self.assertEqual(context.exception.error_code, INVALID_RESOURCE_TOKEN)

    def test_get_user_id_from_jwt_valid(self):
        claims = stubs.api.jwt_claims()
        user_id = get_user_id_from_jwt(claims)
        self.assertEqual(user_id, claims["sub"])

    def test_get_user_id_from_jwt_empty_claims(self):
        with self.assertRaises(AuthenticationError) as context:
            get_user_id_from_jwt({})
        self.assertEqual(context.exception.error_code, EMPTY_TOKEN)

    def test_get_user_id_from_jwt_none_claims(self):
        with self.assertRaises(AuthenticationError) as context:
            get_user_id_from_jwt(None)
        self.assertEqual(context.exception.error_code, EMPTY_TOKEN)

    def test_get_user_id_from_jwt_missing_sub(self):
        claims = stubs.api.jwt_claims()
        claims.pop("sub")
        with self.assertRaises(AuthenticationError) as context:
            get_user_id_from_jwt(claims)
        self.assertEqual(context.exception.error_code, NO_USER_ID_IN_TOKEN)

    def test_get_chat_type_from_jwt_valid(self):
        claims = stubs.api.jwt_claims()
        chat_type = get_chat_type_from_jwt(claims)
        self.assertEqual(chat_type, "telegram")

    def test_get_chat_type_from_jwt_none_claims(self):
        chat_type = get_chat_type_from_jwt(None)
        self.assertIsNone(chat_type)

    def test_get_chat_type_from_jwt_missing_platform(self):
        claims = stubs.api.jwt_claims()
        claims.pop("platform")
        chat_type = get_chat_type_from_jwt(claims)
        self.assertIsNone(chat_type)

    def test_whatsapp_webhook_challenge_success(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        self.addCleanup(setattr, config, "whatsapp_auth_key", config.whatsapp_auth_key)
        config.whatsapp_auth_key = SecretStr("test-token")
        challenge = verify_whatsapp_webhook_challenge("subscribe", "test-challenge", "test-token")
        self.assertEqual(challenge, "test-challenge")

    def test_whatsapp_webhook_challenge_invalid_token(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        self.addCleanup(setattr, config, "whatsapp_auth_key", config.whatsapp_auth_key)
        config.whatsapp_auth_key = SecretStr("correct-token")
        with self.assertRaises(HTTPException) as context:
            verify_whatsapp_webhook_challenge("subscribe", "test-challenge", "wrong-token")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Webhook verification failed")

    def test_whatsapp_webhook_challenge_invalid_mode(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        self.addCleanup(setattr, config, "whatsapp_auth_key", config.whatsapp_auth_key)
        config.whatsapp_auth_key = SecretStr("test-token")
        with self.assertRaises(HTTPException) as context:
            verify_whatsapp_webhook_challenge("unsubscribe", "test-challenge", "test-token")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Webhook verification failed")

    def test_whatsapp_webhook_challenge_auth_disabled(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = False
        challenge = verify_whatsapp_webhook_challenge("subscribe", "test-challenge", "any-token")
        self.assertEqual(challenge, "test-challenge")

    def test_whatsapp_signature_verification_success(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        self.addCleanup(setattr, config, "whatsapp_app_secret", config.whatsapp_app_secret)
        config.whatsapp_app_secret = SecretStr("test-secret")
        payload = b"test payload"
        signature = HMAC(b"test-secret", payload, sha256).hexdigest()
        verify_whatsapp_signature(payload, f"sha256={signature}")

    def test_whatsapp_signature_verification_invalid_signature(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        self.addCleanup(setattr, config, "whatsapp_app_secret", config.whatsapp_app_secret)
        config.whatsapp_app_secret = SecretStr("test-secret")
        payload = b"test payload"
        with self.assertRaises(HTTPException) as context:
            verify_whatsapp_signature(payload, "sha256=wrong-signature")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Invalid signature")

    def test_whatsapp_signature_verification_missing_header(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        payload = b"test payload"
        with self.assertRaises(HTTPException) as context:
            verify_whatsapp_signature(payload, None)
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Missing signature header")

    def test_whatsapp_signature_verification_invalid_format(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = True
        payload = b"test payload"
        with self.assertRaises(HTTPException) as context:
            verify_whatsapp_signature(payload, "invalid-format")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Invalid signature format")

    def test_whatsapp_signature_verification_auth_disabled(self):
        self.addCleanup(setattr, config, "whatsapp_must_auth", config.whatsapp_must_auth)
        config.whatsapp_must_auth = False
        payload = b"test payload"
        verify_whatsapp_signature(payload, None)

    def test_invalid_gumroad_auth_key(self):
        self.addCleanup(setattr, config, "gumroad_must_auth", config.gumroad_must_auth)
        config.gumroad_must_auth = True
        self.addCleanup(setattr, config, "gumroad_auth_key", config.gumroad_auth_key)
        config.gumroad_auth_key = SecretStr("VALI-DKEY")
        with self.assertRaises(HTTPException) as context:
            verify_gumroad_auth_key("NOTA-VALI-DKEY")
        self.assertEqual(context.exception.status_code, HTTP_403_FORBIDDEN)
        self.assertEqual(context.exception.detail, "Invalid auth token")

    def test_disabled_gumroad_auth_key(self):
        self.addCleanup(setattr, config, "gumroad_must_auth", config.gumroad_must_auth)
        config.gumroad_must_auth = False
        verify_gumroad_auth_key("any-token")

    def test_valid_gumroad_auth_key(self):
        self.addCleanup(setattr, config, "gumroad_must_auth", config.gumroad_must_auth)
        config.gumroad_must_auth = True
        self.addCleanup(setattr, config, "gumroad_auth_key", config.gumroad_auth_key)
        config.gumroad_auth_key = SecretStr("VALI-DKEY")
        verify_gumroad_auth_key("VALI-DKEY")
