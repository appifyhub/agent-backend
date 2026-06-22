from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import requests

from db.model.chat_config import ChatConfigDB
from db.schema.chat_message import ChatMessage, ChatMessageSave
from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.supported_files import KNOWN_FILE_FORMATS
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
from util.functions import detect_image_format, first_key_with_value

ATTACHMENT_URL_EXPIRATION = 23 * 60 * 60  # 23 hours in seconds
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

    def __reupload_media_and_store(
        self,
        media_bytes: bytes,
        attachment: ChatMessageAttachment,
        detected_format: str | None = None,
    ) -> ChatMessageAttachment:
        msg_id_short = attachment.message_id[:10]
        local_id_short = str(attachment.id)[:10]
        extension = f".{detected_format}" if detected_format else ""
        filename = f"{msg_id_short}_{local_id_short}{extension}"
        file_uploader = self.__di.file_uploader(media_bytes, filename)
        uploaded_url = file_uploader.execute()
        permanent_url_until = int((datetime.now() + timedelta(seconds = ATTACHMENT_URL_EXPIRATION)).timestamp())
        attachment = replace(attachment, last_url = uploaded_url, last_url_until = permanent_url_until)
        attachment = self.__di.chat_message_attachment_repo.save(attachment)
        log.t(f"Successfully re-uploaded media to permanent storage: {uploaded_url}")
        return attachment

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
        message_save = ChatMessageSave(
            message_id = first_message.id,
            chat_id = chat_config.chat_id,
            author_id = THE_AGENT.id,
            sent_at = datetime.now(),
            text = text,
        )
        message_db = self.__di.chat_message_crud.save(message_save)
        return ChatMessage.model_validate(message_db)

    def __store_attachment_for_sent_media(
        self,
        message_id: str,
        chat_id: UUID,
        media_url: str,
    ) -> ChatMessageAttachment:
        log.t("Storing attachment for sent media...")
        local_id = f"agent_media_wa_{message_id}"
        wa_url_until = int((datetime.now() + timedelta(seconds = WHATSAPP_MEDIA_URL_EXPIRATION)).timestamp())

        # Download media to detect format and prepare for re-upload
        media_bytes: bytes | None = None
        detected_format: str | None = None
        detected_mime_type: str | None = None
        try:
            response = requests.get(media_url, timeout = config.web_timeout_s * 3)
            if response.status_code == 200:
                media_bytes = response.content
                if media_bytes:
                    detected_format = detect_image_format(media_bytes)
                    if detected_format and detected_format in KNOWN_FILE_FORMATS:
                        detected_mime_type = KNOWN_FILE_FORMATS[detected_format]
                        log.t(f"Detected media format: {detected_format} -> {detected_mime_type}")
        except Exception as e:
            log.w(f"Failed to download media from {media_url}", e)

        # Store initial attachment with original WhatsApp URL (short-lived)
        attachment = ChatMessageAttachment(
            id = local_id,
            external_id = message_id,
            message_id = message_id,
            chat_id = chat_id,
            last_url = media_url,
            last_url_until = wa_url_until,
            mime_type = detected_mime_type,
        )
        attachment = self.__di.chat_message_attachment_repo.save(attachment)

        # Try to re-upload to a more permanent storage
        if media_bytes:
            try:
                attachment = self.__reupload_media_and_store(media_bytes, attachment, detected_format)
            except Exception as e:
                log.w("Failed to re-upload media to permanent storage, keeping original URL", e)

        return attachment

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

    def refresh_attachment(
        self,
        attachment: ChatMessageAttachment,
    ) -> ChatMessageAttachment:
        log.d(f"Refreshing attachment '{attachment.id}'")

        # check if instance data is already fresh
        if not attachment.has_stale_data:
            log.t(f"Attachment '{attachment.id}': data is already fresh")
            # we store it anyway because it may contain fresh data from the API
            return self.__di.chat_message_attachment_repo.save(attachment)

        # data is stale or missing, we need to fetch the attachment data from remote
        if not attachment.external_id:
            raise InternalError("No external ID provided for the attachment", MISSING_EXTERNAL_ATTACHMENT_ID)
        log.t(f"Refreshing attachment data for external ID '{attachment.external_id}'")

        # Get media info from WhatsApp API
        media_info: MediaInfo | None = self.__di.whatsapp_bot_api.get_media_info(attachment.external_id)
        if not media_info:
            raise ExternalServiceError(f"Could not get media info for external ID '{attachment.external_id}'", MEDIA_INFO_FAILED)  # noqa: E501

        # Download media bytes
        media_bytes: bytes | None = self.__di.whatsapp_bot_api.download_media_bytes(media_info.url)
        if not media_bytes:
            raise ExternalServiceError(f"Could not download media for external ID '{attachment.external_id}'", MEDIA_DOWNLOAD_FAILED)  # noqa: E501

        # Determine format from mime type
        detected_format: str | None = None
        if media_info.mime_type:
            detected_format = first_key_with_value(KNOWN_FILE_FORMATS, media_info.mime_type)

        # Populate all metadata before re-upload
        size = media_info.file_size or attachment.size
        mime_type = media_info.mime_type or attachment.mime_type
        updated_attachment = replace(attachment, size = size, mime_type = mime_type)
        if not updated_attachment.extension and updated_attachment.mime_type:
            extension = first_key_with_value(KNOWN_FILE_FORMATS, updated_attachment.mime_type) or updated_attachment.extension
            updated_attachment = replace(updated_attachment, extension = extension)

        # Re-upload to permanent storage (also saves to DB with all metadata)
        return self.__reupload_media_and_store(media_bytes, updated_attachment, detected_format)

    @staticmethod
    def _nearest_hour_epoch() -> int:
        now = datetime.now()
        last_hour_mark: datetime = now.replace(minute = 0, second = 0, microsecond = 0)
        next_hour_mark: datetime = last_hour_mark + timedelta(hours = 1)
        log.t(f"Nearest hour at {now} is {next_hour_mark}")
        return int(next_hour_mark.timestamp())
