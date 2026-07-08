from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import requests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.message.chat_message import ChatMessage
from features.chat.whatsapp.model.media_info import MediaInfo
from features.chat.whatsapp.model.response import MessageResponse
from features.integrations.integration_config import THE_AGENT
from util import log
from util.config import config
from util.error_codes import (
    ATTACHMENT_NOT_FOUND,
    CHAT_CONFIG_NOT_FOUND,
    MEDIA_DOWNLOAD_FAILED,
    MEDIA_INFO_FAILED,
    MISSING_EXTERNAL_ATTACHMENT_ID,
)
from util.errors import ExternalServiceError, InternalError, NotFoundError

WHATSAPP_MEDIA_URL_EXPIRATION = 5 * 60  # 5 minutes in seconds


class WhatsAppBotSDK:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    # === API functions ===

    def send_text_message(
        self,
        chat_id: int | str,
        text: str,
    ) -> ChatMessage:
        sent_message = self.__di.whatsapp_bot_api.send_text_message(
            recipient_id = str(chat_id),
            text = text,
        )
        return self.__store_api_response_as_message(sent_message, text = text, recipient_id = str(chat_id))

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
    ) -> ChatMessage:
        sent_message = self.__di.whatsapp_bot_api.send_image(
            recipient_id = str(chat_id),
            image_url = photo_url,
            caption = caption,
        )
        message = self.__store_api_response_as_message(sent_message, text = caption or "", recipient_id = str(chat_id))
        self.__store_attachment_for_sent_media(
            message_id = message.message_id,
            chat_id = message.chat_id,
            media_url = photo_url,
        )
        return message

    def send_document(
        self,
        chat_id: int | str,
        document_url: str,
        caption: str | None = None,
    ) -> ChatMessage:
        sent_message = self.__di.whatsapp_bot_api.send_document(
            recipient_id = str(chat_id),
            document_url = document_url,
            caption = caption,
        )
        message = self.__store_api_response_as_message(sent_message, text = caption or "", recipient_id = str(chat_id))
        self.__store_attachment_for_sent_media(
            message_id = message.message_id,
            chat_id = message.chat_id,
            media_url = document_url,
        )
        return message

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None):
        self.__di.whatsapp_bot_api.send_reaction(
            recipient_id = str(chat_id),
            message_id = str(message_id),
            emoji = reaction or "",
        )

    def mark_as_read(self, message_id: str) -> None:
        self.__di.whatsapp_bot_api.mark_as_read(message_id = message_id)

    def send_button_link(self, chat_id: int | str, link_url: str, button_text: str = "⚙️") -> ChatMessage:
        text = f"{button_text} {link_url}"
        sent_message = self.__di.whatsapp_bot_api.send_text_message(
            recipient_id = str(chat_id),
            text = text,
        )
        return self.__store_api_response_as_message(sent_message, text = text, recipient_id = str(chat_id))

    # === Data utilities ===

    def __store_api_response_as_message(
        self,
        raw_api_response: MessageResponse,
        text: str,
        recipient_id: str,
    ) -> ChatMessage:
        log.t("Storing API message data...")
        first_message = raw_api_response.messages[0]
        chat_config = self.__di.chat_config_repo.get_by_external_identifiers(
            external_id = recipient_id,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        if not chat_config:
            raise NotFoundError(f"Chat config not found for WhatsApp recipient: {recipient_id}", CHAT_CONFIG_NOT_FOUND)
        message = ChatMessage(
            message_id = first_message.id,
            chat_id = chat_config.chat_id,
            author_id = THE_AGENT.id,
            sent_at = datetime.now(),
            text = text,
        )
        return self.__di.chat_message_repo.save(message)

    def refresh_attachments_by_ids(self, attachment_ids: list[str]) -> list[ChatMessageAttachment]:
        log.d(f"Refreshing {len(attachment_ids)} attachments by IDs")
        attachments: list[ChatMessageAttachment] = []
        for attachment_id in attachment_ids:
            attachment = self.__di.chat_message_attachment_repo.get(attachment_id)
            if not attachment:
                raise NotFoundError(f"Attachment with ID '{attachment_id}' not found in DB", ATTACHMENT_NOT_FOUND)
            attachments.append(attachment)
        return self.refresh_attachment_instances(attachments)

    def refresh_attachment_instances(self, attachments: list[ChatMessageAttachment]) -> list[ChatMessageAttachment]:
        log.d(f"Refreshing {len(attachments)} attachment instances")
        return [self.refresh_attachment(attachment) for attachment in attachments]

    def refresh_attachment(self, attachment: ChatMessageAttachment) -> ChatMessageAttachment:
        log.d(f"Refreshing attachment '{attachment.id}'")

        if self.__di.chat_message_attachment_service.is_own_storage_uri(attachment.last_url):
            log.t(f"Attachment '{attachment.id}': data is already in attachment storage")
            return attachment

        # check if instance data is already fresh
        if not attachment.has_stale_data:
            log.t(f"Attachment '{attachment.id}': data is already fresh")
            # we store it anyway because it may contain fresh data from the API
            return self.__di.chat_message_attachment_service.save(attachment)

        # data is stale or missing, we need to fetch the attachment data from remote: get media info from WhatsApp API
        if not attachment.external_id:
            raise InternalError("No external ID provided for the attachment", MISSING_EXTERNAL_ATTACHMENT_ID)
        log.t(f"Refreshing attachment data for external ID '{attachment.external_id}'")
        media_info: MediaInfo | None = self.__di.whatsapp_bot_api.get_media_info(attachment.external_id)
        if not media_info:
            raise ExternalServiceError(f"Could not get media info for external ID '{attachment.external_id}'", MEDIA_INFO_FAILED)  # noqa: E501

        # download the actual media bytes
        media_bytes: bytes | None = self.__di.whatsapp_bot_api.download_media_bytes(media_info.url)
        if not media_bytes:
            raise ExternalServiceError(f"Could not download media for external ID '{attachment.external_id}'", MEDIA_DOWNLOAD_FAILED)  # noqa: E501

        # update attachment metadata with fresh info
        updated_attachment = replace(
            attachment,
            mime_type = media_info.mime_type or attachment.mime_type,  # prefer fresh value
            extension = None if media_info.mime_type else attachment.extension,  # prefer fresh resolution
        )

        # store in service-owned storage (also saves to DB with all metadata)
        stored_attachment = self.__di.chat_message_attachment_service.save(updated_attachment, media_bytes)
        log.t(f"Successfully stored media attachment '{stored_attachment.id}'")
        return stored_attachment

    def __store_attachment_for_sent_media(self, message_id: str, chat_id: UUID, media_url: str) -> ChatMessageAttachment:
        log.t("Storing attachment for sent media...")
        # download media bytes to prepare for storage
        media_bytes: bytes
        try:
            response = requests.get(media_url, timeout = config.web_timeout_s * 3)
            if response.status_code != 200 or not response.content:
                log.w(
                    f"Could not download sent media for message '{message_id}': "
                    f"status={response.status_code}, bytes={len(response.content or b"")}",
                )
                raise ExternalServiceError(f"Could not download sent media for message '{message_id}'", MEDIA_DOWNLOAD_FAILED)
            media_bytes = response.content
        except ExternalServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError(f"Could not download sent media for message '{message_id}'", MEDIA_DOWNLOAD_FAILED) from e

        # prepare the initial attachment metadata (keeping the original short-lived URL)
        last_url_until = int((datetime.now() + timedelta(seconds = WHATSAPP_MEDIA_URL_EXPIRATION)).timestamp())
        attachment = ChatMessageAttachment(
            external_id = message_id,
            uploader_user_id = self.__di.invoker.id,
            message_id = message_id,
            chat_id = chat_id,
            last_url = media_url,
            last_url_until = last_url_until,
        )

        # store the attachment and the media bytes (if available) in our storage
        return self.__di.chat_message_attachment_service.save(attachment, media_bytes)

    @staticmethod
    def _nearest_hour_epoch() -> int:
        now = datetime.now()
        last_hour_mark: datetime = now.replace(minute = 0, second = 0, microsecond = 0)
        next_hour_mark: datetime = last_hour_mark + timedelta(hours = 1)
        log.t(f"Nearest hour at {now} is {next_hour_mark}")
        return int(next_hour_mark.timestamp())
