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


class ChatMessageAttachmentService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def validate_public_read_claims(self, token_claims: PublicResourceTokenClaims) -> None:
        if token_claims.purpose != ATTACHMENT_PUBLIC_READ_PURPOSE:
            raise AuthenticationError("Invalid attachment public token purpose", INVALID_RESOURCE_TOKEN)

    def save(
        self,
        attachment: ChatMessageAttachment,
        content: bytes | None = None,
    ) -> ChatMessageAttachment:
        mime_type, extension = resolve_file_type(
            mime_type = attachment.mime_type,
            extension = attachment.extension,
            uri = attachment.last_url or attachment.uri,
            content = content,
        )
        updated_attachment = replace(
            attachment,
            mime_type = mime_type,
            extension = extension,
        )

        if content is not None:
            if not content:
                raise ValidationError("Attachment content must be provided", MISSING_CONTENT)
            # persist the content in the file storage
            self.__di.attachment_storage.put(updated_attachment, content)
            # regenerate public URL metadata
            public_url = self.create_public_url(updated_attachment)
            updated_attachment = replace(
                updated_attachment,
                size = len(content),
                last_url = public_url.url,
                last_url_until = public_url.valid_until,
            )

        # finally, store in DB whatever we have at the end of this process
        return self.__di.chat_message_attachment_repo.save(updated_attachment)

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
        attachment = self.__di.chat_message_attachment_repo.get(attachment_id)
        if attachment is None:
            raise NotFoundError(f"Attachment '{attachment_id}' not found", ATTACHMENT_NOT_FOUND)

        membership = self.__di.chat_membership_service.get(self.__di.invoker.id, attachment.chat_id)
        if membership is None:
            message = f"User '{self.__di.invoker.id.hex}' is not a member of chat '{attachment.chat_id.hex}'"
            raise AuthorizationError(message, NOT_CHAT_MEMBER)

        mime_type, _ = resolve_file_type(
            mime_type = attachment.mime_type,
            extension = attachment.extension,
            uri = attachment.uri,
        )
        return ResolvedAttachmentStream(
            stream = self.__di.attachment_storage.open(attachment),
            media_type = mime_type or "application/octet-stream",
        )
