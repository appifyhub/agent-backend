from uuid import UUID

from api.auth import CliTokenClaims
from api.mapper.cli_chat_api_mapper import delivery_to_api, domain_to_api
from api.model.cli_chat_response import CliChatResponse
from api.model.cli_connect_payload import CliConnectPayload
from api.model.cli_connect_response import CliConnectResponse
from api.model.cli_notify_chat_payload import CliNotifyChatPayload
from api.model.cli_notify_response import CliNotifyResponse
from api.model.cli_notify_user_payload import CliNotifyUserPayload
from di.di import DI
from features.integrations.integrations import resolve_any_external_handle
from util import log
from util.error_codes import CLI_ACCESS_REVOKED
from util.errors import AuthenticationError


class CliController:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def connect(self, payload: CliConnectPayload) -> CliConnectResponse:
        log.d("Connecting a CLI")
        connection = self.__di.cli_access_service.connect(payload.ttl_as_text, payload.device_id, payload.hostname, payload.os)
        handle, _ = resolve_any_external_handle(connection.user)
        return CliConnectResponse(
            token = connection.token,
            expires_at = connection.expires_at,
            user_id = connection.user.id.hex,
            user_display_name = connection.user.full_name or handle or connection.user.id.hex,
            credit_balance = connection.user.credit_balance,
        )

    def require_valid_cli_token(self, claims: CliTokenClaims) -> None:
        user = self.__di.authorization_service.validate_user(claims.user_id)
        if claims.generation != user.cli_token_generation:
            raise AuthenticationError("CLI access was revoked", CLI_ACCESS_REVOKED)

    def revoke_all(self, user_id_hex: str) -> None:
        log.d(f"Revoking all CLI access for user '{user_id_hex}'")
        self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        self.__di.cli_access_service.revoke_all()

    def list_chats(self) -> list[CliChatResponse]:
        log.d(f"Listing CLI chats for user '{self.__di.invoker.id.hex}'")
        chats = self.__di.authorization_service.get_authorized_chats(self.__di.invoker)
        return [domain_to_api(chat) for chat in chats]

    def notify_user(self, hostname: str, user_id_hex: str, payload: CliNotifyUserPayload) -> CliNotifyResponse:
        log.d(f"Notifying user '{user_id_hex}' from a CLI")
        self.__di.authorization_service.authorize_for_user(self.__di.invoker, user_id_hex)
        delivery = self.__di.cli_notify_service.notify_invoker(hostname, payload.message, payload.platform)
        return delivery_to_api(delivery.chat, delivery.user)

    def notify_chat(self, hostname: str, chat_id: str | UUID, payload: CliNotifyChatPayload) -> CliNotifyResponse:
        log.d(f"Notifying chat '{chat_id}' for user '{self.__di.invoker.id.hex}' from a CLI")
        delivery = self.__di.cli_notify_service.notify_chat(hostname, chat_id, payload.message)
        return delivery_to_api(delivery.chat, delivery.user)
