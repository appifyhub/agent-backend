from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import BinaryIO

import requests

from api.auth import create_public_attachment_token, verify_public_attachment_token
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.supported_files import is_supported_mime_type, resolve_file_type
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util import log
from util.config import config
from util.error_codes import (
    ATTACHMENT_NOT_FOUND,
    MALFORMED_ATTACHMENT_ID,
    MEDIA_DOWNLOAD_FAILED,
    MISSING_ATTACHMENT_IDS,
    MISSING_CONTENT,
    NOT_CHAT_MEMBER,
)
from util.errors import AuthorizationError, ExternalServiceError, NotFoundError, ValidationError


@dataclass(frozen = True)
class ResolvedAttachmentStream:
    stream: BinaryIO
    media_type: str


@dataclass(frozen = True)
class AttachmentPublicUrl:
    url: str
    valid_until: int


@dataclass(frozen = True)
class RemoteAttachmentContent:
    content: bytes
    response_mime_type: str | None = None


RemoteUrlFetcher = Callable[[str], RemoteAttachmentContent]


class ChatMessageAttachmentService:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def get(self, attachment: ChatMessageAttachment | str) -> ChatMessageAttachment:
        if isinstance(attachment, ChatMessageAttachment):
            return attachment
        if not attachment:
            raise ValidationError("Attachment ID cannot be empty", MALFORMED_ATTACHMENT_ID)
        stored_attachment = self.__di.chat_message_attachment_repo.get(attachment)
        if stored_attachment is None:
            raise NotFoundError(f"Attachment '{attachment}' not found", ATTACHMENT_NOT_FOUND)
        return stored_attachment

    def stream_attachment(self, attachment: ChatMessageAttachment | str) -> ResolvedAttachmentStream:
        attachment = self.get(attachment)

        # validate that the invoker has rights to access this attachment
        membership = self.__di.chat_membership_service.get(self.__di.invoker.id, attachment.chat_id)
        if membership is None:
            message = f"User '{self.__di.invoker.id.hex}' is not a member of chat '{attachment.chat_id.hex}'"
            raise AuthorizationError(message, NOT_CHAT_MEMBER)

        return ResolvedAttachmentStream(
            stream = self.__di.attachment_storage.open(attachment),
            media_type = attachment.mime_type or "application/octet-stream",
        )

    def save(
        self,
        attachment: ChatMessageAttachment | str,
        content: bytes | None = None,
        remote_url: str | None = None,
        remote_url_fetcher: RemoteUrlFetcher | None = None,
    ) -> ChatMessageAttachment:
        attachment = self.get(attachment)

        # first, check if this attachment is already fully stored using its external ID
        if attachment.external_id:
            existing = self.__di.chat_message_attachment_repo.get_by_external_id(attachment.chat_id, attachment.external_id)
            if existing and self.is_own_storage_uri(existing.last_url):
                return existing

        # second, check if the remote URL points to one of our own attachments
        if content is None and remote_url:
            internal_attachment = self.__find_internal_attachment(remote_url)
            if internal_attachment:
                return internal_attachment

        # next, we prepare content and metadata to the best of our ability
        remote_content: RemoteAttachmentContent | None = self.__fetch_remote_content(content, remote_url, remote_url_fetcher)
        remote_mime_type = remote_content.response_mime_type if remote_content else None
        remote_content_bytes = remote_content.content if remote_content else None
        mime_type, extension = resolve_file_type(
            mime_type = attachment.mime_type or remote_mime_type,
            extension = attachment.extension,
            uri = remote_url or attachment.last_url or attachment.uri,
            content = remote_content_bytes,
        )

        # next, update the local attachment instance with the latest resolved metadata
        updated_attachment = replace(
            attachment,
            mime_type = mime_type,
            extension = extension,
            uploader_user_id = attachment.uploader_user_id or self.__di.invoker.id,
        )

        # next, check if we need to store the media bytes in our storage
        if remote_content_bytes:
            previous_our_uri = attachment.uri if self.is_own_storage_uri(attachment.last_url) else None
            updated_attachment = replace(
                updated_attachment,
                size = len(remote_content_bytes),
                last_url = f"s3://{config.s3_bucket}/{updated_attachment.uri}",
            )
            self.__di.attachment_storage.put(updated_attachment, remote_content_bytes)
            # a changed extension changes the storage key — drop the now-orphaned old object
            if previous_our_uri and previous_our_uri != updated_attachment.uri:
                self.__delete_storage_objects([attachment])

        # finally, store the updated attachment in our database
        return self.__di.chat_message_attachment_repo.save(updated_attachment)

    def create_public_url(self, attachment: ChatMessageAttachment | str) -> AttachmentPublicUrl:
        attachment = self.get(attachment)
        valid_until = datetime.now() + timedelta(seconds = config.attachment_public_token_ttl_seconds)
        token = create_public_attachment_token(
            chat_id = attachment.chat_id.hex,
            attachment_id = attachment.id,
            issuer_user_id = self.__di.invoker.id.hex,
            ttl_seconds = config.attachment_public_token_ttl_seconds,
        )
        return AttachmentPublicUrl(
            url = f"{config.public_api_base_url}/attachments/public/{token}",
            valid_until = int(valid_until.timestamp()),
        )

    def is_own_public_url(self, url: str | None) -> bool:
        if not url:
            return False
        public_url_prefix = f"{config.public_api_base_url}/attachments/public/"
        token = url.removeprefix(public_url_prefix)
        return url.startswith(public_url_prefix) and bool(token) and "/" not in token

    def is_own_private_url(self, url: str | None) -> bool:
        if not url:
            return False
        private_url_prefix = f"{config.public_api_base_url}/attachments/private/"
        attachment_id = url.removeprefix(private_url_prefix)
        return url.startswith(private_url_prefix) and bool(attachment_id) and "/" not in attachment_id

    def is_own_storage_uri(self, uri: str | None) -> bool:
        if not uri:
            return False
        return uri.startswith(f"s3://{config.s3_bucket}/chats/")

    def resolve_attachments(self, attachment_ids: list[str] | None, urls: list[str] | None) -> list[ChatMessageAttachment]:
        if not attachment_ids and not urls:
            raise ValidationError("No attachment IDs or URLs provided", MISSING_ATTACHMENT_IDS)
        invoker_id = self.__di.invoker.id
        chat_id = self.__di.require_invoker_chat().chat_id
        # resolve local attachments by fetching from the DB
        local_attachments: list[ChatMessageAttachment] = [
            self.get(attachment_id)
            for attachment_id in (attachment_ids or [])
        ]
        # resolve the remote attachments by pulling content for each
        remote_attachments: list[ChatMessageAttachment] = [
            self.save(
                attachment = ChatMessageAttachment(chat_id = chat_id, uploader_user_id = invoker_id, last_url = url),
                remote_url = url,
            )
            for url in (urls or [])
        ]
        # return all of them together
        return local_attachments + remote_attachments

    def __fetch_remote_content(
        self,
        content: bytes | None,
        remote_url: str | None,
        remote_url_fetcher: RemoteUrlFetcher | None,
    ) -> RemoteAttachmentContent | None:
        # first we try to use content, if provided
        if content is not None:
            # content is sent, but it must not be empty
            if not content:
                raise ValidationError("Attachment content must be provided", MISSING_CONTENT)
            return RemoteAttachmentContent(content)
        # if URL is not provided, there's nothing to fetch
        if not remote_url:
            return None

        # 'save' prevents internal attachments from being requested here, so it's safe to directly fetch
        fetcher_function = remote_url_fetcher or self.__fetch_remote_url
        fetched_content = fetcher_function(remote_url)
        if not fetched_content.content:
            raise ExternalServiceError("Attachment content could not be accessed", MEDIA_DOWNLOAD_FAILED)
        fetched_mime_type = (
            fetched_content.response_mime_type
            if is_supported_mime_type(fetched_content.response_mime_type)
            else None
        )

        # finally, we have content to return
        return RemoteAttachmentContent(fetched_content.content, fetched_mime_type)

    @staticmethod
    def __fetch_remote_url(remote_url: str) -> RemoteAttachmentContent:
        try:
            response = requests.get(remote_url, headers = DEFAULT_HEADERS, timeout = config.web_timeout_s * 4)
            if response.status_code != 200 or not response.content:
                raise ExternalServiceError("Attachment content could not be accessed", MEDIA_DOWNLOAD_FAILED)

            content_type = response.headers.get("Content-Type", "")
            response_mime_type = content_type.split(";")[0].strip() if content_type else None
            if not is_supported_mime_type(response_mime_type):
                response_mime_type = None
            return RemoteAttachmentContent(response.content, response_mime_type)
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Attachment content could not be accessed", MEDIA_DOWNLOAD_FAILED) from e

    def cleanup_old_attachments(self, cutoff: datetime) -> int:
        deleted = self.__di.chat_message_attachment_repo.delete_stale(cutoff)
        self.__delete_storage_objects(deleted)
        return len(deleted)

    def cleanup_orphaned_attachments(self, cutoff: datetime) -> int:
        deleted = self.__di.chat_message_attachment_repo.delete_stale(cutoff, only_orphans = True)
        self.__delete_storage_objects(deleted)
        return len(deleted)

    def __delete_storage_objects(self, attachments: list[ChatMessageAttachment]) -> None:
        for attachment in attachments:
            try:
                self.__di.attachment_storage.delete(attachment)
            except Exception as e:
                log.e(f"Could not delete storage object for attachment '{attachment.id}'", e)

    def __find_internal_attachment(self, url: str) -> ChatMessageAttachment | None:
        if self.is_own_storage_uri(url):
            filename = url.rsplit("/", 1)[-1]
            if not filename:
                return None
            return self.__di.chat_message_attachment_repo.get(filename.rsplit(".", 1)[0])
        if self.is_own_public_url(url):
            token = url.rsplit("/", 1)[-1]
            claims = verify_public_attachment_token(token)
            return self.__di.chat_message_attachment_repo.get(claims.attachment_id)
        if self.is_own_private_url(url):
            return self.__di.chat_message_attachment_repo.get(url.rsplit("/", 1)[-1])
        return None
