from copy import deepcopy
from pathlib import Path
from typing import Any

from stubs import external

from features.chat.telegram.model.chat_member import ChatMember
from features.videos.video_file_utils import VideoMetadata
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeTelegramBotAPI:

    _messages: dict[str, dict[str, Any]]
    downloads: dict[str, bytes | Exception | None]
    members: dict[tuple[str, str], ChatMember | Exception]
    statuses: dict[str, str]
    reactions: dict[tuple[str, str], str | None]
    delivery_errors: dict[str, Exception]

    def __init__(self):
        self._messages = {}
        self.downloads = {}
        self.members = {}
        self.statuses = {}
        self.reactions = {}
        self.delivery_errors = {}

    def get_sent_message(self, message_id: str) -> dict[str, Any]:
        return deepcopy(self._messages[message_id])

    def get_sent_messages(self, chat_id: int | str) -> list[dict[str, Any]]:
        return [deepcopy(message) for message in self._messages.values() if str(message["chat_id"]) == str(chat_id)]

    def send_text_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
        link_preview_options: dict | None = None,
    ) -> dict:
        return self._send({
            "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
            "disable_notification": disable_notification, "link_preview_options": link_preview_options,
        })

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> dict:
        return self._send({
            "chat_id": chat_id, "photo_url": photo_url, "caption": caption,
            "parse_mode": parse_mode, "disable_notification": disable_notification,
        })

    def send_document(
        self,
        chat_id: int | str,
        document_url: str | None = None,
        document_path: str | None = None,
        filename: str | None = None,
        parse_mode: str = "markdown",
        thumbnail: str | None = None,
        caption: str | None = None,
        disable_notification: bool = False,
    ) -> dict:
        return self._send({
            "chat_id": chat_id, "document_url": document_url, "filename": filename,
            "content": Path(document_path).read_bytes() if document_path is not None else None,
            "parse_mode": parse_mode, "thumbnail": thumbnail, "caption": caption,
            "disable_notification": disable_notification,
        })

    def send_video(
        self,
        chat_id: int | str,
        video_path: str,
        metadata: VideoMetadata,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> dict:
        return self._send({
            "chat_id": chat_id, "content": Path(video_path).read_bytes(), "metadata": metadata,
            "caption": caption, "parse_mode": parse_mode, "disable_notification": disable_notification,
        })

    def send_button_link(self, chat_id: int | str, link_url: str, button_text: str = "⚙️") -> dict:
        return self._send({"chat_id": chat_id, "link_url": link_url, "button_text": button_text})

    def set_status_typing(self, chat_id: int | str) -> dict:
        self.statuses[str(chat_id)] = "typing"
        return {"ok": True}

    def set_status_uploading_image(self, chat_id: int | str) -> dict:
        self.statuses[str(chat_id)] = "upload_photo"
        return {"ok": True}

    def set_status_uploading_video(self, chat_id: int | str) -> dict:
        self.statuses[str(chat_id)] = "upload_video"
        return {"ok": True}

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None) -> dict:
        self.reactions[(str(chat_id), str(message_id))] = reaction
        return {"ok": True}

    def get_chat_member(self, chat_id: int | str, user_id: int | str) -> ChatMember:
        key = (str(chat_id), str(user_id))
        if key not in self.members:
            raise InternalError(f"No Telegram member configured for {key}", DI_DEPENDENCY_NOT_MET)
        member = self.members[key]
        if isinstance(member, Exception):
            raise member
        return member.model_copy(deep = True)

    def download_file(self, file_id: str) -> bytes | None:
        if file_id not in self.downloads:
            raise InternalError(f"No Telegram download configured for '{file_id}'", DI_DEPENDENCY_NOT_MET)
        content = self.downloads[file_id]
        if isinstance(content, Exception):
            raise content
        return content

    def _send(self, message: dict[str, Any]) -> dict:
        error = self.delivery_errors.get(str(message["chat_id"]))
        if error is not None:
            raise error
        message_id = str(len(self._messages) + 1)
        self._messages[message_id] = deepcopy(message)
        return external.telegram_message_response(message_id = int(message_id))
