from dataclasses import replace
from datetime import datetime
from uuid import UUID

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.message.chat_message import ChatMessage
from features.chat.message.formatted_chat_message import FormattedAttachmentPart, FormattedChatMessage, FormattedTextPart
from features.chat.whatsapp.model.response import MessageResponse
from features.integrations.integration_config import THE_AGENT
from util import log


class WhatsAppBotSDK:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    # === API functions ===

    def send_text_message(
        self,
        chat_config: ChatConfig,
        text: str,
    ) -> ChatMessage:
        sent_message = self.__di.whatsapp_bot_api.send_text_message(recipient_id = chat_config.external_id, text = text)
        return self.__store_api_response_as_message(sent_message, text = text, chat_id = chat_config.chat_id)

    def send_photo(
        self,
        chat_config: ChatConfig,
        attachment: ChatAttachment,
        caption: str | None = None,
    ) -> ChatMessage:
        # the attachment is already archived; expose it via a public URL for delivery
        public_url = self.__di.chat_attachment_service.create_public_url(attachment).url
        # sending will generate a real message ID
        sent_message = self.__di.whatsapp_bot_api.send_image(
            recipient_id = chat_config.external_id,
            image_url = public_url,
            caption = caption,
        )
        content = self.__media_message_content(attachment, caption)
        message = self.__store_api_response_as_message(sent_message, text = content.to_text(), chat_id = chat_config.chat_id)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def send_document(
        self,
        chat_config: ChatConfig,
        attachment: ChatAttachment,
        caption: str | None = None,
    ) -> ChatMessage:
        # the attachment is already archived; expose it via a public URL for delivery
        public_url = self.__di.chat_attachment_service.create_public_url(attachment).url
        # sending will generate a real message ID
        sent_message = self.__di.whatsapp_bot_api.send_document(
            recipient_id = chat_config.external_id,
            document_url = public_url,
            caption = caption,
        )
        content = self.__media_message_content(attachment, caption)
        message = self.__store_api_response_as_message(sent_message, text = content.to_text(), chat_id = chat_config.chat_id)
        # we should now quickly update the attachment record with the new ID
        self.__di.chat_attachment_service.save(replace(attachment, message_id = message.message_id))
        return message

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None):
        self.__di.whatsapp_bot_api.send_reaction(
            recipient_id = str(chat_id),
            message_id = str(message_id),
            emoji = reaction or "",
        )

    def mark_as_read(self, message_id: str) -> None:
        self.__di.whatsapp_bot_api.mark_as_read(message_id = message_id)

    def send_button_link(self, chat_config: ChatConfig, link_url: str, button_text: str = "⚙️") -> ChatMessage:
        text = f"{button_text} {link_url}"
        sent_message = self.__di.whatsapp_bot_api.send_text_message(
            recipient_id = chat_config.external_id,
            text = text,
        )
        return self.__store_api_response_as_message(sent_message, text = text, chat_id = chat_config.chat_id)

    # === Data utilities ===

    def __store_api_response_as_message(
        self,
        raw_api_response: MessageResponse,
        text: str,
        chat_id: UUID,
    ) -> ChatMessage:
        log.t("Storing API message data...")
        first_message = raw_api_response.messages[0]
        message = ChatMessage(
            message_id = first_message.id,
            chat_id = chat_id,
            author_id = THE_AGENT.id,
            sent_at = datetime.now(),
            text = text,
        )
        return self.__di.chat_message_repo.save(message)

    # noinspection PyMethodMayBeStatic
    def __media_message_content(
        self,
        attachment: ChatAttachment,
        caption: str | None,
    ) -> FormattedChatMessage:
        parts = []
        if caption:
            parts.append(FormattedTextPart(text = caption))
        parts.append(FormattedAttachmentPart.from_attachments([attachment]))
        return FormattedChatMessage(parts = parts)
