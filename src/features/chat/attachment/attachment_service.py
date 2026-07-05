from dataclasses import dataclass
from typing import BinaryIO

from api.auth import PublicResourceTokenClaims
from di.di import DI
from features.chat.supported_files import resolve_file_type
from util.error_codes import ATTACHMENT_NOT_FOUND, INVALID_RESOURCE_TOKEN, NOT_CHAT_MEMBER
from util.errors import AuthenticationError, AuthorizationError, NotFoundError

ATTACHMENT_PUBLIC_READ_PURPOSE = "attachment-public-read"


@dataclass(frozen = True)
class ResolvedAttachmentStream:
    stream: BinaryIO
    media_type: str


class AttachmentService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_public_read_claims(self, token_claims: PublicResourceTokenClaims) -> None:
        if token_claims.purpose != ATTACHMENT_PUBLIC_READ_PURPOSE:
            raise AuthenticationError("Invalid attachment public token purpose", INVALID_RESOURCE_TOKEN)

    def open_attachment(self, attachment_id: str) -> ResolvedAttachmentStream:
        # must fetch this first to get the attachment's chat_id
        attachment = self.__di.chat_message_attachment_repo.get(attachment_id)
        if attachment is None:
            raise NotFoundError(f"Attachment '{attachment_id}' not found", ATTACHMENT_NOT_FOUND)

        # chat is known now, so we can check if the invoker has access to it
        membership = self.__di.chat_membership_service.get(self.__di.invoker.id, attachment.chat_id)
        if membership is None:
            message = f"User '{self.__di.invoker.id.hex}' is not a member of chat '{attachment.chat_id.hex}'"
            raise AuthorizationError(message, NOT_CHAT_MEMBER)

        # we can proceed to open the attachment now
        mime_type, _ = resolve_file_type(
            mime_type = attachment.mime_type,
            extension = attachment.extension,
            uri = attachment.uri,
        )
        return ResolvedAttachmentStream(
            stream = self.__di.attachment_storage.open(attachment),
            media_type = mime_type or "application/octet-stream",
        )
