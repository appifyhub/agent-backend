from typing import Any


class ServiceError(Exception):
    error_code: int
    http_status: int
    emoji: str

    def __init__(
        self,
        message: str,
        error_code: int,
        http_status: int = 500,
        emoji: str = "⚠️",
    ):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status
        self.emoji = emoji

    def __str__(self) -> str:
        return self.to_log_string()

    def to_log_string(self) -> str:
        from util.config import config
        cause_str = f" # Caused by: {self.__cause__}" if self.__cause__ else ""
        raw = f"[E{self.error_code}] {self.emoji} {super().__str__()}{cause_str}"
        for secret in config.all_secrets():
            value = secret.get_secret_value()
            if value:
                raw = raw.replace(value, "****")
        return raw

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "emoji": self.emoji,
        }

    def to_llm_dict(self) -> dict[str, Any]:
        return {
            "result": "Error",
            "error_code": self.error_code,
            "emoji": self.emoji,
            "information": str(self),
        }


class ValidationError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "✏️"):
        super().__init__(message, error_code, http_status = 422, emoji = emoji)


class BadRequestError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "✏️"):
        super().__init__(message, error_code, http_status = 400, emoji = emoji)


class NotFoundError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "🔍"):
        super().__init__(message, error_code, http_status = 404, emoji = emoji)


class AuthorizationError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "🔒"):
        super().__init__(message, error_code, http_status = 403, emoji = emoji)


class AuthenticationError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "🔑"):
        super().__init__(message, error_code, http_status = 401, emoji = emoji)


class ExternalServiceError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "🌐"):
        super().__init__(message, error_code, http_status = 502, emoji = emoji)


class RateLimitError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "⏳"):
        super().__init__(message, error_code, http_status = 429, emoji = emoji)


class ConfigurationError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "⚙️"):
        super().__init__(message, error_code, http_status = 500, emoji = emoji)


class InternalError(ServiceError):
    def __init__(self, message: str, error_code: int, emoji: str = "⚠️"):
        super().__init__(message, error_code, http_status = 500, emoji = emoji)
