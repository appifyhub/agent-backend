import unittest

from pydantic import SecretStr

from util.config import config
from util.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ExternalServiceError,
    InternalError,
    NotFoundError,
    RateLimitError,
    ServiceError,
    ValidationError,
)


class ServiceErrorTest(unittest.TestCase):

    def test_to_log_string_without_cause(self):
        error = ServiceError("Something went wrong", error_code = 42, emoji = "🫖")

        self.assertEqual(error.to_log_string(), "[E42] 🫖 Something went wrong")

    def test_to_log_string_with_cause(self):
        try:
            try:
                raise ValueError("root cause")
            except ValueError as cause:
                raise ServiceError("Something went wrong", error_code = 42, emoji = "🫖") from cause
        except ServiceError as error:
            self.assertEqual(error.to_log_string(), "[E42] 🫖 Something went wrong # Caused by: root cause")

    def test_str_equals_to_log_string(self):
        error = ServiceError("Something went wrong", error_code = 42, emoji = "🫖")

        self.assertEqual(str(error), error.to_log_string())

    def test_to_log_string_scrubs_secrets(self):
        self.addCleanup(setattr, config, "api_key", config.api_key)
        config.api_key = SecretStr("abc123secret")
        error = ServiceError("Token abc123secret leaked", error_code = 42, emoji = "🫖")

        result = error.to_log_string()

        self.assertNotIn("abc123secret", result)
        self.assertIn("****", result)

    def test_to_api_dict(self):
        error = ServiceError("Something went wrong", error_code = 42, emoji = "🫖")

        result = error.to_api_dict()

        self.assertEqual(result["error_code"], 42)
        self.assertEqual(result["emoji"], "🫖")
        self.assertIn("Something went wrong", result["message"])

    def test_to_llm_dict(self):
        error = ServiceError("Something went wrong", error_code = 42, emoji = "🫖")

        result = error.to_llm_dict()

        self.assertEqual(result["result"], "Error")
        self.assertEqual(result["error_code"], 42)
        self.assertEqual(result["emoji"], "🫖")
        self.assertIn("Something went wrong", result["information"])


class SubclassDefaultsTest(unittest.TestCase):

    def test_validation_error(self):
        error = ValidationError("msg", error_code = 1)

        self.assertEqual(error.http_status, 422)
        self.assertEqual(error.emoji, "✏️")

    def test_not_found_error(self):
        error = NotFoundError("msg", error_code = 1)

        self.assertEqual(error.http_status, 404)
        self.assertEqual(error.emoji, "🔍")

    def test_authorization_error(self):
        error = AuthorizationError("msg", error_code = 1)

        self.assertEqual(error.http_status, 403)
        self.assertEqual(error.emoji, "🔒")

    def test_authentication_error(self):
        error = AuthenticationError("msg", error_code = 1)

        self.assertEqual(error.http_status, 401)
        self.assertEqual(error.emoji, "🔑")

    def test_external_service_error(self):
        error = ExternalServiceError("msg", error_code = 1)

        self.assertEqual(error.http_status, 502)
        self.assertEqual(error.emoji, "🌐")

    def test_rate_limit_error(self):
        error = RateLimitError("msg", error_code = 1)

        self.assertEqual(error.http_status, 429)
        self.assertEqual(error.emoji, "⏳")

    def test_configuration_error(self):
        error = ConfigurationError("msg", error_code = 1)

        self.assertEqual(error.http_status, 500)
        self.assertEqual(error.emoji, "⚙️")

    def test_internal_error(self):
        error = InternalError("msg", error_code = 1)

        self.assertEqual(error.http_status, 500)
        self.assertEqual(error.emoji, "⚠️")
