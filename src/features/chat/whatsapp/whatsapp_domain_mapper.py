from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData
from features.chat.message.formatted_chat_message import FormattedAttachmentPart, FormattedChatMessage, FormattedTextPart
from features.chat.whatsapp.model.message import Message as WhatsAppMessage
from features.chat.whatsapp.model.update import Update
from features.chat.whatsapp.model.value import Value
from features.users.user_remote_data import UserRemoteData
from util import log
from util.functions import normalize_phone_number


class WhatsAppDomainMapper:

    @dataclass(kw_only = True)
    class Result:

        chat: ChatConfigRemoteData
        author: UserRemoteData | None
        message: ChatMessageRemoteData
        attachments: list[ChatAttachmentRemoteData]
        formatted_message: FormattedChatMessage | None = None
        replied_to_message_id: str | None = None

    def map_update(self, update: Update) -> list[Result]:
        log.t(f"Mapping WhatsApp update: {update}")
        if not update.entry:
            log.w(f"  No entries found in update: {update}")
            return []

        # Collect and map all messages from all entries/changes
        results: list[WhatsAppDomainMapper.Result] = []
        for entry in update.entry:
            log.t(f"  Processing update entry '{entry.id}'...")
            if not entry.changes:
                log.w(f"  No changes found in entry '{entry.id}'")
                continue
            for change in entry.changes:
                log.t(f"  Processing change '{change.field}' in entry '{entry.id}'...")
                value = change.value
                if not value or not value.messages:
                    log.w(f"  No messages found in {value.messaging_product} value")
                    continue
                for message in value.messages:
                    result_chat = self.map_chat(message, value)
                    result_author = self.map_author(message, value)
                    result_attachments = self.map_attachments(message)
                    result_formatted_message = self.map_content(message, result_attachments)
                    result_message = self.map_message(message, result_formatted_message)
                    replied_to_message_id = message.context.id if message.context else None
                    results.append(
                        WhatsAppDomainMapper.Result(
                            chat = result_chat,
                            author = result_author,
                            message = result_message,
                            formatted_message = result_formatted_message,
                            attachments = result_attachments,
                            replied_to_message_id = replied_to_message_id,
                        ),
                    )
        if not results:
            log.w(f"  No messages found in update: {update}")
        return results

    def map_message(
        self,
        message: WhatsAppMessage,
        formatted_message: FormattedChatMessage | None = None,
    ) -> ChatMessageRemoteData:
        log.t(f"  Mapping message: {message}")
        formatted_message = formatted_message or self.map_content(message)
        return ChatMessageRemoteData(
            message_id = message.id,
            sent_at = datetime.fromtimestamp(int(message.timestamp)),
            text = formatted_message.to_text(),
        )

    # noinspection PyMethodMayBeStatic
    def map_author(self, message: WhatsAppMessage, value: Value) -> UserRemoteData | None:
        full_name: str | None = None
        wa_id: str
        if value.contacts:
            contact = value.contacts[0]
            full_name = contact.profile.name if contact.profile else None
            wa_id = contact.wa_id
        else:
            wa_id = message.from_
        if not wa_id:
            log.w(f"  No WhatsApp user ID found for message '{message.id}'")
            return None
        phone_number = SecretStr(wa_id) if self._is_phone_number(wa_id) else None
        return UserRemoteData(
            full_name = full_name,
            whatsapp_user_id = wa_id,
            whatsapp_phone_number = phone_number,
        )

    def map_content(
        self,
        message: WhatsAppMessage,
        attachments: list[ChatAttachmentRemoteData] | None = None,
    ) -> FormattedChatMessage:
        parts = []
        if message.text and message.text.body:
            parts.append(FormattedTextPart(text = message.text.body))
        for media in [
            message.image,
            message.video,
            message.audio,
            message.document,
        ]:
            if media and media.caption:
                parts.append(FormattedTextPart(text = media.caption))
        attachments = attachments if attachments is not None else self.map_attachments(message)
        if attachments:
            parts.append(FormattedAttachmentPart.from_remote_data(attachments))
        log.t(f"  Mapping message text: {parts}")
        return FormattedChatMessage(parts = parts)

    def map_chat(self, message: WhatsAppMessage, value: Value) -> ChatConfigRemoteData:
        log.t(f"  Mapping chat for message: {message}")
        external_id = message.from_
        contacts = value.contacts or []
        first_contact = contacts[0] if contacts else None
        profile_name = first_contact.profile.name if first_contact and first_contact.profile else None
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
