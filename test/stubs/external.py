from typing import Any

from fastapi.security import HTTPAuthorizationCredentials

from features.chat.telegram.model.attachment.audio import Audio as TelegramAudio
from features.chat.telegram.model.attachment.document import Document as TelegramDocument
from features.chat.telegram.model.attachment.photo_size import PhotoSize as TelegramPhotoSize
from features.chat.telegram.model.attachment.video import Video as TelegramVideo
from features.chat.telegram.model.attachment.voice import Voice as TelegramVoice
from features.chat.telegram.model.chat import Chat as TelegramChat
from features.chat.telegram.model.message import Message as TelegramMessage
from features.chat.telegram.model.text_quote import TextQuote as TelegramTextQuote
from features.chat.telegram.model.update import Update as TelegramUpdate
from features.chat.telegram.model.user import User as TelegramUser
from features.chat.whatsapp.model.attachment.media_attachment import MediaAttachment as WhatsAppMediaAttachment
from features.chat.whatsapp.model.attachment.text import Text as WhatsAppText
from features.chat.whatsapp.model.change import Change as WhatsAppChange
from features.chat.whatsapp.model.contact import Contact as WhatsAppContact
from features.chat.whatsapp.model.context import Context as WhatsAppContext
from features.chat.whatsapp.model.entry import Entry as WhatsAppEntry
from features.chat.whatsapp.model.message import Message as WhatsAppMessage
from features.chat.whatsapp.model.metadata import Metadata as WhatsAppMetadata
from features.chat.whatsapp.model.profile import Profile as WhatsAppProfile
from features.chat.whatsapp.model.response import (
    ContactResponse as WhatsAppContactResponse,
)
from features.chat.whatsapp.model.response import (
    MessageResponse as WhatsAppMessageResponse,
)
from features.chat.whatsapp.model.response import (
    SentMessageResponse as WhatsAppSentMessageResponse,
)
from features.chat.whatsapp.model.update import Update as WhatsAppUpdate
from features.chat.whatsapp.model.value import Value as WhatsAppValue


def whatsapp_profile(**overrides: Any) -> WhatsAppProfile:
    defaults = {
        "name": "New User",
    }
    return WhatsAppProfile(**(defaults | overrides))


def whatsapp_contact(**overrides: Any) -> WhatsAppContact:
    defaults = {
        "profile": whatsapp_profile(),
        "wa_id": "1",
    }
    return WhatsAppContact(**(defaults | overrides))


def whatsapp_metadata(**overrides: Any) -> WhatsAppMetadata:
    defaults = {
        "display_phone_number": "123",
        "phone_number_id": "phone-id",
    }
    return WhatsAppMetadata(**(defaults | overrides))


def whatsapp_text(**overrides: Any) -> WhatsAppText:
    defaults = {
        "body": "Hello from Mark Johnson.",
    }
    return WhatsAppText(**(defaults | overrides))


def whatsapp_context(**overrides: Any) -> WhatsAppContext:
    defaults = {
        "from": None,
        "id": "message-122",
    }
    return WhatsAppContext(**(defaults | overrides))


def whatsapp_media_attachment(**overrides: Any) -> WhatsAppMediaAttachment:
    defaults = {
        "id": "whatsapp-media-123",
        "caption": None,
        "mime_type": "image/jpeg",
        "sha256": None,
        "filename": None,
        "voice": None,
    }
    return WhatsAppMediaAttachment(**(defaults | overrides))


def whatsapp_message(**overrides: Any) -> WhatsAppMessage:
    defaults: dict[str, Any] = {
        "from": "15551234567",
        "id": "whatsapp-message-123",
        "timestamp": "1768478400",
        "type": "text",
    }
    if "text" not in overrides:
        defaults["text"] = whatsapp_text()
    return WhatsAppMessage(**(defaults | overrides))


def whatsapp_value(**overrides: Any) -> WhatsAppValue:
    defaults = {
        "messaging_product": "whatsapp",
        "metadata": whatsapp_metadata(),
        "contacts": [whatsapp_contact()],
        "messages": [],
    }
    return WhatsAppValue(**(defaults | overrides))


def whatsapp_change(**overrides: Any) -> WhatsAppChange:
    defaults: dict[str, Any] = {
        "field": "messages",
    }
    if "value" not in overrides:
        defaults["value"] = whatsapp_value()
    return WhatsAppChange(**(defaults | overrides))


def whatsapp_entry(**overrides: Any) -> WhatsAppEntry:
    defaults: dict[str, Any] = {
        "id": "whatsapp-business-account-123",
    }
    if "changes" not in overrides:
        defaults["changes"] = [whatsapp_change()]
    return WhatsAppEntry(**(defaults | overrides))


def whatsapp_update(**overrides: Any) -> WhatsAppUpdate:
    defaults: dict[str, Any] = {
        "object": "whatsapp_business_account",
    }
    if "entry" not in overrides:
        defaults["entry"] = [whatsapp_entry()]
    return WhatsAppUpdate(**(defaults | overrides))


def whatsapp_contact_response(**overrides: Any) -> WhatsAppContactResponse:
    defaults = {
        "input": "+15551234567",
        "wa_id": "15551234567",
    }
    return WhatsAppContactResponse(**(defaults | overrides))


def whatsapp_sent_message_response(**overrides: Any) -> WhatsAppSentMessageResponse:
    defaults = {
        "id": "whatsapp-message-123",
        "message_status": "accepted",
    }
    return WhatsAppSentMessageResponse(**(defaults | overrides))


def whatsapp_message_response(**overrides: Any) -> WhatsAppMessageResponse:
    defaults: dict[str, Any] = {
        "messaging_product": "whatsapp",
    }
    if "contacts" not in overrides:
        defaults["contacts"] = [whatsapp_contact_response()]
    if "messages" not in overrides:
        defaults["messages"] = [whatsapp_sent_message_response()]
    return WhatsAppMessageResponse(**(defaults | overrides))


def telegram_chat(**overrides: Any) -> TelegramChat:
    defaults = {
        "id": 123456789,
        "type": "private",
        "title": None,
        "username": None,
        "first_name": None,
        "last_name": None,
    }
    return TelegramChat(**(defaults | overrides))


def telegram_user(**overrides: Any) -> TelegramUser:
    defaults = {
        "id": 123456789,
        "is_bot": False,
        "first_name": "Mark",
        "last_name": None,
        "username": None,
        "language_code": None,
    }
    return TelegramUser(**(defaults | overrides))


def telegram_audio(**overrides: Any) -> TelegramAudio:
    defaults = {
        "file_id": "telegram-audio-123",
        "file_unique_id": "telegram-unique-audio-123",
        "file_name": None,
        "mime_type": None,
        "file_size": None,
    }
    return TelegramAudio(**(defaults | overrides))


def telegram_document(**overrides: Any) -> TelegramDocument:
    defaults = {
        "file_id": "telegram-file-123",
        "file_unique_id": "telegram-unique-file-123",
        "file_name": None,
        "mime_type": None,
        "file_size": None,
    }
    return TelegramDocument(**(defaults | overrides))


def telegram_voice(**overrides: Any) -> TelegramVoice:
    defaults = {
        "file_id": "telegram-voice-123",
        "file_unique_id": "telegram-unique-voice-123",
        "mime_type": None,
        "file_size": None,
    }
    return TelegramVoice(**(defaults | overrides))


def telegram_video(**overrides: Any) -> TelegramVideo:
    defaults = {
        "file_id": "telegram-video-123",
        "file_unique_id": "telegram-unique-video-123",
        "width": 1920,
        "height": 1080,
        "duration": 12,
        "file_name": None,
        "mime_type": None,
        "file_size": None,
    }
    return TelegramVideo(**(defaults | overrides))


def telegram_photo_size(**overrides: Any) -> TelegramPhotoSize:
    defaults = {
        "file_id": "telegram-photo-123",
        "file_unique_id": "telegram-unique-photo-123",
        "width": 1280,
        "height": 720,
        "file_size": None,
    }
    return TelegramPhotoSize(**(defaults | overrides))


def telegram_text_quote(**overrides: Any) -> TelegramTextQuote:
    defaults = {
        "text": "Selected quote",
        "position": 0,
        "entities": None,
    }
    return TelegramTextQuote(**(defaults | overrides))


def telegram_message(**overrides: Any) -> TelegramMessage:
    defaults: dict[str, Any] = {
        "message_id": 123,
        "text": None,
        "date": 1_768_478_400,
    }
    if "chat" not in overrides:
        defaults["chat"] = telegram_chat()
    return TelegramMessage(**(defaults | overrides))


def telegram_update(**overrides: Any) -> TelegramUpdate:
    defaults = {
        "update_id": 123,
    }
    return TelegramUpdate(**(defaults | overrides))


def http_authorization_credentials(**overrides: Any) -> HTTPAuthorizationCredentials:
    defaults = {
        "scheme": "Bearer",
        "credentials": "valid-token",
    }
    return HTTPAuthorizationCredentials(**(defaults | overrides))
