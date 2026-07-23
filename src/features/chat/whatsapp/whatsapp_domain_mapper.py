from datetime import datetime

from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.whatsapp.model.message import Message as WhatsAppMessage
from features.chat.whatsapp.model.value import Value
from features.users.user_remote_data import UserRemoteData
from util import log
from util.functions import normalize_phone_number


class WhatsAppDomainMapper:

    def map_message(self, message: WhatsAppMessage) -> ChatMessageRemoteData:
        log.t(f"  Mapping message: {message}")
        text = "\n\n".join(
            part
            for part in [
                message.text.body if message.text else None,
                message.image.caption if message.image else None,
                message.video.caption if message.video else None,
                message.audio.caption if message.audio else None,
                message.document.caption if message.document else None,
            ]
            if part
        )
        return ChatMessageRemoteData(
            message_id = message.id,
            sent_at = datetime.fromtimestamp(int(message.timestamp)),
            text = text,
            replied_to_message_id = message.context.id if message.context else None,
        )

    # noinspection PyMethodMayBeStatic
    def map_author(self, message: WhatsAppMessage, value: Value) -> UserRemoteData | None:
        wa_id = message.from_
        if not wa_id:
            log.w(f"  No WhatsApp user ID found for message '{message.id}'")
            return None
        contact = next((contact for contact in value.contacts or [] if contact.wa_id == wa_id), None)
        full_name = contact.profile.name if contact and contact.profile else None
        phone_number = SecretStr(wa_id) if self._is_phone_number(wa_id) else None
        return UserRemoteData(
            full_name = full_name,
            whatsapp_user_id = wa_id,
            whatsapp_phone_number = phone_number,
        )

    def map_chat(self, message: WhatsAppMessage, value: Value) -> ChatConfigRemoteData:
        log.t(f"  Mapping chat for message: {message}")
        external_id = message.from_
        contact = next((contact for contact in value.contacts or [] if contact.wa_id == external_id), None)
        profile_name = contact.profile.name if contact and contact.profile else None
        title = self.resolve_chat_name(external_id, profile_name)
        return ChatConfigRemoteData(
            external_id = external_id,
            title = title,
            is_private = True,  # WhatsApp only supports private chats
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )

    # noinspection PyMethodMayBeStatic
    def resolve_chat_name(
        self,
        chat_id: str,
        contact_name: str | None,
    ) -> str:
        if contact_name:
            return contact_name
        return f"#{chat_id}"

    def map_attachments(self, message: WhatsAppMessage) -> list[ChatAttachmentRemoteData]:
        attachments: list[ChatAttachmentRemoteData] = []
        for media_type, media in [
            ("audio", message.audio),
            ("document", message.document),
            ("image", message.image),
            ("video", message.video),
        ]:
            if media:
                log.t(f"  Mapping {media_type}: {media.id}")
                attachments.append(
                    self.map_to_attachment(
                        media_id = media.id,
                        message_id = message.id,
                        mime_type = media.mime_type,
                    ),
                )
        return attachments

    # noinspection PyMethodMayBeStatic
    def map_to_attachment(
        self,
        media_id: str,
        message_id: str,
        mime_type: str | None,
    ) -> ChatAttachmentRemoteData:
        log.t(f"    Creating attachment from media_id: {media_id}")
        return ChatAttachmentRemoteData(
            external_id = media_id,
            message_id = message_id,
            size = None,  # filled after refresh
            last_url = None,  # filled after refresh
            mime_type = mime_type,
        )

    def _is_phone_number(self, wa_id: str) -> bool:
        normalized = normalize_phone_number(wa_id)
        return normalized == wa_id and wa_id.isdigit()
