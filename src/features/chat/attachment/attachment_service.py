from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import BinaryIO

from api.auth import PublicResourceTokenClaims, create_public_resource_token
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.supported_files import resolve_file_type
from util.config import config
from util.error_codes import ATTACHMENT_NOT_FOUND, INVALID_RESOURCE_TOKEN, MISSING_CONTENT, NOT_CHAT_MEMBER
from util.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError

ATTACHMENT_PUBLIC_READ_PURPOSE = "attachment-public-read"


@dataclass(frozen = True)
class ResolvedAttachmentStream:
    stream: BinaryIO
    media_type: str


@dataclass(frozen = True)
class AttachmentPublicUrl:
    url: str
    valid_until: int


class AttachmentService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_public_read_claims(self, token_claims: PublicResourceTokenClaims) -> None:
        if token_claims.purpose != ATTACHMENT_PUBLIC_READ_PURPOSE:
            raise AuthenticationError("Invalid attachment public token purpose", INVALID_RESOURCE_TOKEN)

    def save_attachment_bytes(self, attachment: ChatMessageAttachment, content: bytes) -> ChatMessageAttachment:
        if not content:
            raise ValidationError("Attachment content must be provided", MISSING_CONTENT)

        # resolve the latest, most correct metadata
        mime_type, extension = resolve_file_type(
            mime_type = attachment.mime_type,
            extension = attachment.extension,
            uri = attachment.uri,
            content = content,
        )
        stored_attachment = replace(
            attachment,
            size = len(content),
            mime_type = mime_type,
            extension = extension,
        )

        # store the updated attachment content in the attachment storage
        self.__di.attachment_storage.put(stored_attachment, content)

        # create a new public, time-limited and signed URL for the attachment, and save it
        public_url = self.create_public_url(stored_attachment)
        complete_attachment = self.__di.chat_message_attachment_repo.save(replace(
            stored_attachment,
            last_url = public_url.url,
            last_url_until = public_url.valid_until,
        ))
        return complete_attachment

    def create_public_url(self, attachment: ChatMessageAttachment) -> AttachmentPublicUrl:
        valid_until = datetime.now() + timedelta(seconds = config.attachment_public_token_ttl_seconds)
        token = create_public_resource_token(
            resource_id = attachment.id,
            purpose = ATTACHMENT_PUBLIC_READ_PURPOSE,
            principal_id = self.__di.invoker_id,
            ttl_seconds = config.attachment_public_token_ttl_seconds,
        )
        base_url = config.public_api_base_url.rstrip("/")
        return AttachmentPublicUrl(
            url = f"{base_url}/attachments/public/{token}",
            valid_until = int(valid_until.timestamp()),
        )

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
