from copy import deepcopy
from typing import Any

from stubs import external

from features.chat.whatsapp.model.response import MarkAsReadResponse, MessageResponse
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeWhatsAppBotAPI:

    _messages: dict[str, dict[str, Any]]
    downloads: dict[str, bytes | Exception | None]
    reactions: dict[tuple[str, str], str]
    read_messages: set[str]

    def __init__(self):
        self._messages = {}
        self.downloads = {}
        self.reactions = {}
        self.read_messages = set()

    def get_sent_message(self, message_id: str) -> dict[str, Any]:
        return deepcopy(self._messages[message_id])

    def get_sent_messages(self, recipient_id: str) -> list[dict[str, Any]]:
        return [deepcopy(message) for message in self._messages.values() if message["recipient_id"] == recipient_id]

    def send_text_message(self, recipient_id: str, text: str) -> MessageResponse:
        return self._send({"recipient_id": recipient_id, "text": text})

    def send_image(self, recipient_id: str, image_url: str, caption: str | None = None) -> MessageResponse:
        return self._send({"recipient_id": recipient_id, "image_url": image_url, "caption": caption})

    def send_document(
        self,
        recipient_id: str,
        document_url: str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> MessageResponse:
        return self._send({"recipient_id": recipient_id, "document_url": document_url, "caption": caption, "filename": filename})

    def send_video(self, recipient_id: str, video_url: str, caption: str | None = None) -> MessageResponse:
        return self._send({"recipient_id": recipient_id, "video_url": video_url, "caption": caption})

    def send_reaction(self, recipient_id: str, message_id: str, emoji: str) -> MessageResponse:
        self.reactions[(recipient_id, message_id)] = emoji
        return external.whatsapp_message_response()

    def mark_as_read(self, message_id: str) -> MarkAsReadResponse:
        self.read_messages.add(message_id)
        return external.whatsapp_mark_as_read_response()

    def download_media(self, media_id: str) -> bytes | None:
        if media_id not in self.downloads:
            raise InternalError(f"No WhatsApp download configured for '{media_id}'", DI_DEPENDENCY_NOT_MET)
        content = self.downloads[media_id]
        if isinstance(content, Exception):
            raise content
        return content

    def _send(self, message: dict[str, Any]) -> MessageResponse:
        message_id = f"whatsapp-message-{len(self._messages) + 1}"
        self._messages[message_id] = deepcopy(message)
        return external.whatsapp_message_response(messages = [external.whatsapp_sent_message_response(id = message_id)])
